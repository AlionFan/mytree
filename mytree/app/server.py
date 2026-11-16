"""小树同学本机演示服务；静态页面和同源 JSON API。"""
import json
import os
import re
import mimetypes
import gzip
import hashlib
from functools import lru_cache
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import ai, profile, junior, agent, cards, contract, review, explorer, speech, access, quiz, card_learning, auth, page_reading, question_search, visual, family, teaching_memory, personal_review, parent_access, billing, uploads
from .errors import DomainError
from .reading_registry import registry as readings, ConfirmationError, new_id
from .knowledge import CAUSES
from .documents import preview_pdf
from .pipeline import diagnose, prepare_lesson
from .practice import check_answer, for_cause

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, '..', 'web')
MAX_BODY = 6_100_000
MAX_STEPS = 12
STUDENT_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
PAGES = {'/', '/tree', '/parent', '/plan','/explore','/uploads'}


@lru_cache(maxsize=48)
def _static_representation(filename, modified_ns, size, compressed):
    data=Path(filename).read_bytes()
    if compressed:data=gzip.compress(data,compresslevel=6,mtime=0)
    return data, '"'+hashlib.sha256(data).hexdigest()+'"'


def _accepts_gzip(value):
    preferences={}
    for entry in value.lower().split(','):
        parts=[part.strip() for part in entry.split(';')]
        if not parts[0]:continue
        quality=1.0
        for parameter in parts[1:]:
            if parameter.startswith('q='):
                try:quality=float(parameter[2:])
                except ValueError:quality=0
        preferences[parts[0]]=quality
    return preferences.get('gzip',preferences.get('*',0))>0


class MyTreeHTTPServer(ThreadingHTTPServer):
    # Browsers open several asset connections at once; the Python 3.12 default
    # backlog of five can reset parallel requests when a second tab is opened.
    request_queue_size=128
    daemon_threads=True


def _clean_student(value):
    if value is None:
        return 'demo'
    return value if isinstance(value, str) and STUDENT_RE.fullmatch(value) else None


def _text(value, name, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name}不能为空，且不能超过 {limit} 个字符')
    return value.strip()


class Handler(BaseHTTPRequestHandler):
    server_version = 'mytree/0.3'

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, ctype='application/json; charset=utf-8', extra_headers=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        if code not in (204,304):self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Cache-Control',(extra_headers or {}).get('Cache-Control','no-store'))
        for key,value in (extra_headers or {}).items():
            if key!='Cache-Control':self.send_header(key,value)
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Permissions-Policy','camera=(self), microphone=(self)')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if code==401 and not auth.enabled():self.send_header('WWW-Authenticate','Basic realm="MyTree", charset="UTF-8"')
        if getattr(self,'_set_cookie',None):self.send_header('Set-Cookie',self._set_cookie)
        if getattr(self,'_location',None):self.send_header('Location',self._location)
        try:
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('请发送 JSON 格式的请求')
        n = int(self.headers.get('Content-Length') or 0)
        limit = 28_100_000 if urlparse(self.path).path == '/api/files/preview' else 14_100_000 if urlparse(self.path).path=='/api/uploads' else MAX_BODY
        if n>limit and urlparse(self.path).path=='/api/recognize/page':raise DomainError('PAYLOAD_TOO_LARGE','图片太大，请降低分辨率后重试。',413)
        if n <= 0 or n > limit:
            raise ValueError('请求内容为空或太大')
        result = json.loads(self.rfile.read(n).decode('utf-8'))
        if not isinstance(result, dict):
            raise ValueError('请求应为 JSON 对象')
        return result

    def _identity(self):
        self.account = None
        if auth.enabled():
            try:
                self.account = auth.session(self.headers.get('Cookie'))
            except (auth.AuthError, OSError, auth.sqlite3.Error):
                self._json(503, {'error':'账号服务暂不可用，请稍后重试。','code':'AUTH_UNAVAILABLE'})
                return False
            if self.account:
                return True
            if urlparse(self.path).path in PAGES:
                self._location = '/login?next=%2Fparent' if urlparse(self.path).path=='/parent' else '/login'
                self._send(303, '')
            else:
                self._json(401, {'error':'请先通过邮箱登录。','code':'AUTH_REQUIRED'})
            return False
        if access.authorized(self.headers.get('Authorization')):
            return True
        self._json(401, {'error':'请先登录。'})
        return False

    def _student(self, value):
        return self.account['profile_id'] if getattr(self,'account',None) else _clean_student(value)

    def _auth_post(self, path):
        body = self._body()
        if len(json.dumps(body)) > 2048:
            raise auth.AuthError('登录请求内容过长。')
        # Only the last proxy-added address is accepted, never a client prefix.
        ip = self.client_address[0]
        if os.environ.get('MYTREE_TRUST_PROXY') == '1':
            ip = self.headers.get('X-Forwarded-For',ip).split(',')[-1].strip()[:128]
        if path == '/api/auth/code':
            return self._json(200, auth.request_code(body.get('email'),ip))
        if path == '/api/auth/verify':
            account, token = auth.verify_code(body.get('email'),body.get('code'),ip)
            self._set_cookie = auth.cookie_header(token)
            return self._json(200, {'ok':True, **account})
        if path == '/api/auth/logout':
            account=auth.session(self.headers.get('Cookie'))
            if account:page_reading.registry.invalidate_owner(account['profile_id'])
            auth.logout(self.headers.get('Cookie'))
            self._set_cookie = auth.cookie_header(clear=True)
            return self._json(200, {'ok':True})
        return self._json(404, {'error':'没有找到这个接口'})

    def _admin_identity(self, page=False):
        if auth.admin_session(self.headers.get('Cookie')):
            return True
        if page:
            self._location='/admin/login'
            self._send(303,'')
        else:
            student=auth.session(self.headers.get('Cookie'))
            self._json(403 if student else 401,{'error':'需要管理员身份。','code':'ADMIN_REQUIRED'})
        return False

    def _admin_post(self,path):
        body=self._body()
        if path=='/api/admin/login':
            ip=self.client_address[0]
            if os.environ.get('MYTREE_TRUST_PROXY')=='1':ip=self.headers.get('X-Forwarded-For',ip).split(',')[-1].strip()[:128]
            token=auth.admin_login(body.get('username'),body.get('password'),ip)
            self._set_cookie=auth.admin_cookie(token)
            return self._json(200,{'ok':True})
        if not self._admin_identity():return
        if path=='/api/admin/logout':
            auth.admin_logout(self.headers.get('Cookie'))
            self._set_cookie=auth.admin_cookie(clear=True)
            return self._json(200,{'ok':True})
        return self._json(404,{'error':'没有找到管理接口。'})

    def do_GET(self):
        if self.path=='/_ready':return self._json(200,{'ok':True})
        u = urlparse(self.path)
        if u.path=='/mail-hero.jpg':return self._file('mail-hero.jpg','image/jpeg')
        if u.path in ('/privacy','/privacy.html'):return self._file('privacy.html','text/html; charset=utf-8')
        if auth.enabled() and u.path in ('/admin/login','/admin-login.js','/admin.js'):
            filename='admin-login.html' if u.path=='/admin/login' else u.path[1:]
            return self._file(filename, 'text/html; charset=utf-8' if filename.endswith('.html') else 'text/javascript; charset=utf-8')
        if auth.enabled() and (u.path=='/admin' or u.path.startswith('/api/admin/')):
            try:
                if not self._admin_identity(page=u.path=='/admin'):return
                if u.path=='/admin':return self._file('admin.html','text/html; charset=utf-8')
                if u.path=='/api/admin/overview':return self._json(200,auth.admin_overview())
                return self._json(404,{'error':'没有找到管理接口。'})
            except (auth.AuthError, OSError, auth.sqlite3.Error):return self._json(503,{'error':'管理服务暂不可用。'})
        if u.path=='/api/billing/catalog':return self._json(200,billing.catalog())
        # Public presentation only; learning pages and APIs retain account checks.
        if u.path in ('/welcome','/pricing','/commerce-guide-2.jpg','/commerce-guide-3.jpg','/commerce-mobile.jpg','/commerce.css','/pricing.js','/home.css','/home.js','/youth.css','/character.js','/guide-1.png','/guide-2.png','/guide-3.png','/guide-real-capture.jpg','/guide-connected-tree.jpg','/home-entry.css','/home-fonts.css','/home-thinking.js'):
            filename = 'home.html' if u.path=='/welcome' else 'pricing.html' if u.path=='/pricing' else u.path[1:]
            return self._file(filename,(mimetypes.guess_type(filename)[0] or 'application/octet-stream')+'; charset=utf-8')
        if u.path.startswith('/fonts/'):
            base=Path(STATIC,'fonts').resolve();target=Path(STATIC,u.path.lstrip('/')).resolve()
            if base not in target.parents or not target.is_file() or target.suffix not in ('.woff2','.css','.txt','.json'):return self._json(404,{'error':'资源不存在'})
            return self._file(str(target),mimetypes.guess_type(target)[0] or 'application/octet-stream')
        if auth.enabled() and u.path=='/':
            try:
                visitor = auth.session(self.headers.get('Cookie'))
            except (auth.AuthError, OSError, auth.sqlite3.Error):
                return self._json(503, {'error':'账号服务暂不可用，请稍后重试。','code':'AUTH_UNAVAILABLE'})
            if not visitor:
                return self._file('home.html','text/html; charset=utf-8')
        if u.path in ('/login','/signup','/login.js','/login.css','/favicon.svg'):
            filename = 'login.html' if u.path in ('/login','/signup') else u.path[1:]
            ctype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            return self._file(filename, ctype+'; charset=utf-8')
        if not self._identity():return
        if u.path=='/uploads':return self._file('uploads.html','text/html; charset=utf-8')
        if u.path in ('/uploads.js','/uploads-capture.js','/uploads.css'):
            return self._file(u.path[1:],'text/css; charset=utf-8' if u.path.endswith('.css') else 'text/javascript; charset=utf-8')
        if u.path=='/api/uploads' or re.fullmatch(r'/api/uploads/[a-f0-9]{32}/(?:image|thumb)',u.path):
            try:
                owner=self._student(None)
                if u.path=='/api/uploads':return self._json(200,uploads.listing(owner,parse_qs(u.query).get('page',['1'])[0]))
                data,mime,extension=uploads.image(owner,u.path.split('/')[3],u.path.endswith('/thumb'))
                return self._send(200,data,mime,{'Cache-Control':'no-store'})
            except DomainError as error:return self._json(error.status,{'error':str(error),'code':error.code})
            except OSError:return self._json(503,{'error':'上传记录暂时无法读取。','code':'UPLOAD_STORAGE_FAILED'})
        if u.path=='/api/billing/me':
            if not self.account:return self._json(401,{'error':'请登录学习账号。'})
            try:return self._json(200,billing.overview(self.account['profile_id']))
            except (OSError,auth.sqlite3.Error):return self._json(503,{'error':'额度暂不可用，请稍后重试。'})
        if u.path=='/api/auth/me':
            return self._json(200, {'user':self.account})
        q = parse_qs(u.query)
        if auth.enabled() and u.path=='/parent':
            try:parent_access.lock(self.account,self.headers.get('Cookie'))
            except auth.AuthError as error:return self._json(error.status,{'error':str(error),'code':error.code})
            except (OSError,auth.sqlite3.Error):return self._json(503,{'error':'家长入口暂不可用，请稍后重试。'})
            self._set_cookie=parent_access.cookie(clear=True)
            return self._file('parent.html','text/html; charset=utf-8')
        if u.path=='/api/parent/status':
            try:return self._json(200,parent_access.status(self.account,self.headers.get('Cookie')))
            except auth.AuthError as error:return self._json(error.status,{'error':str(error),'code':error.code})
            except (OSError,auth.sqlite3.Error):return self._json(503,{'error':'家长入口暂不可用，请稍后重试。'})
        if u.path=='/api/parent/overview':
            try:return self._json(200,family.overview(self.account,self.headers.get('Cookie')))
            except auth.AuthError as error:return self._json(error.status,{'error':str(error),'code':error.code})
            except (OSError, auth.sqlite3.Error):return self._json(503,{'error':'家庭记录暂不可用，请稍后重试。'})
        if u.path in PAGES:
            return self._file('index.html', 'text/html; charset=utf-8')
        if u.path in ('/account.js', '/app.js', '/math-ui.js', '/learning-ui.js','/explorer.js','/explorer-voice.css','/focus-ui.js','/diagrams.js', '/family.js', '/parent.css', '/style.css', '/favicon.svg'):
            ctype = {'/parent.css':'text/css; charset=utf-8','/family.js':'text/javascript; charset=utf-8','/account.js':'text/javascript; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/math-ui.js':'text/javascript; charset=utf-8', '/learning-ui.js':'text/javascript; charset=utf-8', '/style.css': 'text/css; charset=utf-8',
                     '/explorer-voice.css':'text/css; charset=utf-8','/explorer.js':'text/javascript; charset=utf-8','/focus-ui.js':'text/javascript; charset=utf-8','/diagrams.js':'text/javascript; charset=utf-8','/favicon.svg': 'image/svg+xml'}[u.path]
            return self._file(u.path[1:], ctype)
        if u.path.startswith('/vendor/'):
            base=Path(STATIC,'vendor').resolve();target=Path(STATIC,u.path.lstrip('/')).resolve()
            if base not in target.parents or not target.is_file():return self._json(404,{'error':'资源不存在'})
            return self._file(str(target),mimetypes.guess_type(target)[0] or 'application/octet-stream')
        if u.path in ('/healthz' , '/api/capabilities'):
            try:
                caps = ai.capabilities()
                return self._json(200, {'ok': True, 'mode': 'email-preview' if auth.enabled() else 'local-demo', 'math_check': True, **caps,
                                       'page_recognition':True,'page_question_limit':12,'original_search':question_search.capabilities(),'curriculum':'junior-math','topics':37,'message': '整页清晰题自动整理，无需逐题校准；支持的式子由程序核验，其他推理标注为AI分析待核验。'})
            except ai.ModelError as error:
                return self._json(error.status, {'error': str(error), 'code': error.code})
        if u.path == '/api/practice':
            cause = (q.get('cause') or [''])[0]
            if cause not in CAUSES and cause != '':
                return self._json(400, {'error': '未知错因'})
            seed = (q.get('seed') or [None])[0]
            seed = int(seed) if seed and seed.isdigit() and len(seed) < 12 else None
            return self._json(200, for_cause(cause or 'CALC', 3, seed))
        if u.path == '/api/review/today':
            student=self._student((q.get('student') or [None])[0])
            if student is None:return self._json(400,{'error':'学生编号格式不对','code':'INVALID_INPUT'})
            try:return self._json(200,review.today(student))
            except OSError:return self._json(503,{'error':'复习安排暂时无法读取','code':'STORAGE_FAILED'})
            except (ValueError,TypeError):return self._json(400,{'error':'复习设置需要核对','code':'INVALID_INPUT'})
        if u.path=='/api/quiz/lesson':return self._json(410,{'error':'三题检验已停用，请使用巩固练习。','code':'FEATURE_RETIRED'})
        if u.path == '/api/cards':
            student=self._student((q.get('student') or [None])[0])
            if student is None:return self._json(400,{'error':'学生编号格式不对','code':'INVALID_INPUT'})
            try:
                params={key:values[0] for key,values in q.items() if key in ('type','status','cursor','limit')}
                params.setdefault('type','wrong')
                if 'limit' in params:params['limit']=int(params['limit'])
                return self._json(200,cards.list_cards(student,params))
            except (DomainError,contract.ContractError,ValueError) as error:
                return self._json(getattr(error,'status',400),{'error':str(error),'code':getattr(error,'code','INVALID_INPUT')})
            except OSError:return self._json(503,{'error':'卡片暂时无法读取','code':'STORAGE_FAILED'})
        if u.path == '/api/profile':
            student = self._student((q.get('student') or [None])[0])
            if student is None:
                return self._json(400, {'error': '学生编号格式不对'})
            try:
                return self._json(200, profile.get(student))
            except (OSError, ValueError):
                return self._json(503, {'error': '学习档案暂时无法读取，请稍后重试'})
        return self._json(404, {'error': '没有找到这个页面或接口'})

    def _file(self, filename, ctype):
        path=Path(os.path.join(STATIC,filename))
        compressible=path.suffix.lower() in ('.html','.css','.js','.svg')
        compressed=compressible and _accepts_gzip(self.headers.get('Accept-Encoding',''))
        stat=path.stat()
        data,etag=_static_representation(str(path),stat.st_mtime_ns,stat.st_size,compressed)
        headers={}
        if compressible:headers['Vary']='Accept-Encoding'
        if compressed:headers['Content-Encoding']='gzip'
        # Only immutable application files get validators. Pages and JSON remain no-store.
        cacheable=path.suffix.lower() in ('.css','.js','.svg','.woff','.woff2','.ttf','.otf','.png','.jpg','.jpeg','.webp')
        if cacheable:
            scope='private' if getattr(self,'account',None) else 'public'
            headers.update({'Cache-Control':scope+', max-age=0, must-revalidate','ETag':etag})
            candidates=[part.strip().removeprefix('W/') for part in self.headers.get('If-None-Match','').split(',')]
            if etag in candidates or '*' in candidates:return self._send(304,b'',ctype,headers)
        return self._send(200,data,ctype,headers)

    def do_POST(self):
        if auth.enabled():
            expected = os.environ.get('MYTREE_PUBLIC_ORIGIN') or 'http://'+self.headers.get('Host','')
            if self.headers.get('Origin') != expected:
                return self._json(403, {'error':'请从本站页面发起请求。','code':'ORIGIN_REJECTED'})
        elif not access.same_origin(self.headers.get('Origin'),self.headers.get('Host')):
            return self._json(403, {'error':'请从学习桌内发起请求。'})
        try:
            path = urlparse(self.path).path
            if auth.enabled() and path.startswith('/api/admin/'):
                return self._admin_post(path)
            if auth.enabled() and path.startswith('/api/auth/'):
                return self._auth_post(path)
            if not self._identity():return
            body = self._body()
            if path in ('/api/uploads','/api/uploads/delete','/api/uploads/link'):
                action={'/api/uploads':uploads.save,'/api/uploads/delete':uploads.delete,'/api/uploads/link':uploads.link}[path]
                return self._json(200,action(self._student(None),body))
            if path=='/api/billing/selection':
                if not self.account:return self._json(401,{'error':'请登录学习账号。'})
                return self._json(200,billing.selection(self.account['profile_id'],body))
            if path.startswith('/api/parent/'):
                action=path.rsplit('/',1)[-1]
                ip=self.client_address[0]
                if os.environ.get('MYTREE_TRUST_PROXY')=='1':ip=self.headers.get('X-Forwarded-For',ip).split(',')[-1].strip()[:128]
                result,cookie=parent_access.handle(self.account,self.headers.get('Cookie'),action,body,ip)
                if cookie is not None:self._set_cookie=cookie
                return self._json(200,result)
            if path=='/api/questions/search':
                student=self._student(body.get('student'))
                if student is None:raise ValueError('学生编号格式不对')
                return self._json(200,question_search.search(student,body))
            if path in ('/api/recognize/page','/api/study/reading','/api/recognize/page/cancel','/api/recognize/page/resume'):
                student=self._student(body.get('student'))
                if student is None:raise ValueError('学生编号格式不对')
                if path in ('/api/recognize/page','/api/study/reading') and not access.allow_model():return self._json(429,{'error':'请求较多，请稍后重试。','code':'MODEL_BUSY'})
                if path=='/api/recognize/page':
                    result=page_reading.recognize(student,body)
                    if auth.enabled() and not auth.session(self.headers.get('Cookie')):
                        page_reading.registry.invalidate_owner(student)
                        return self._json(401,{'error':'登录已退出，请重新登录。','code':'AUTH_REQUIRED'})
                    return self._json(200,result)
                if path=='/api/study/reading':return self._json(200,page_reading.study(student,body))
                if path=='/api/recognize/page/resume':return self._json(200,page_reading.resume(student,body))
                contract.definition('PageCancelInput',body)
                return self._json(200,readings.cancel_page(student,body['batch_id'],body['source_revision']))
            if self.account:
                if path != '/api/agent':body['student'] = self.account['profile_id']
                if path == '/api/agent' and isinstance(body.get('subject'),dict):
                    body['subject'] = {**body['subject'], 'profile_id':self.account['profile_id']}
            student = self._student(body.get('student'))
            if student is None:
                raise ValueError('学生编号格式不对')
            path = urlparse(self.path).path
            model_path=path in ('/api/explorer/conversation','/api/explorer/observe','/api/speech','/api/recognize','/api/study','/api/chat','/api/visual/lesson') or (path=='/api/agent' and body.get('operation') in ('recognize','study','chat'))
            if model_path and not access.allow_model():return self._json(429,{'error':'这一分钟的请求比较多，请稍等片刻再试。','code':'MODEL_BUSY'})
            if path=='/api/review/personalize':return self._json(200,personal_review.arrange(student))
            if path=='/api/memory':
                action=body.get('action','retrieve')
                if action=='retrieve':return self._json(200,teaching_memory.retrieve(student,body.get('knowledge_id')))
                if action=='preference':return self._json(200,teaching_memory.remember_preference(student,body.get('style')))
                if action=='forget':return self._json(200,teaching_memory.forget(student,body.get('memory_id')))
                raise ValueError('记忆操作不正确。')
            if path=='/api/visual/lesson':return self._json(200,visual.diagram_lesson(student,body))
            if path=='/api/knowledge/learn':return self._json(200,card_learning.handle(student,body))
            if path=='/api/explorer/cancel':
                if not self.account:return self._json(200,{'ok':True})
                return self._json(200,billing.cancel_explorer(student,body))
            if path=='/api/explorer/contexts':return self._json(200,explorer.contexts(student,body))
            if path=='/api/explorer/conversation':
                result=explorer.conversation(student,body)
                if auth.enabled() and not auth.session(self.headers.get('Cookie')):return self._json(401,{'error':'登录已退出，请重新登录。','code':'AUTH_REQUIRED'})
                return self._json(200,result)
            if path=='/api/explorer/observe':return self._json(200,explorer.metered_observe(student,body))
            if path == '/api/agent':
                result,code=agent.handle(body)
                return self._json(code,result)
            if path == '/api/study':
                return self._study(body,student)
            if path == '/api/hint':
                return self._json(200,cards.hint(student,body))
            if path in ('/api/review/ack','/api/review/snooze'):
                action='ack' if path.endswith('/ack') else 'snooze'
                contract.definition('ReviewAckRequest' if action=='ack' else 'ReviewSnoozeRequest',body)
                return self._json(200,review.reminder_action(student,body['reminder_key'],action))
            if path == '/api/cards/edit':
                rid=body.get('request_id') or new_id()
                params={key:value for key,value in body.items() if key not in ('student','request_id')}
                result=agent.invoke(student,'card.edit',params,rid)
                return self._json(200,{'ok':True,**result['output']})
            if path == '/api/feedback':
                return self._json(200,profile.add_feedback(student,_text(body.get('diagnosis_id'),'题目编号',64),body.get('rating'),body.get('issue','')))
            if path == '/api/diagnose':
                return self._diagnose(body, student)
            if path == '/api/practice':
                if not access.allow_model():return self._json(429,{'error':'这一分钟的请求比较多，请稍等片刻再试。','code':'MODEL_BUSY'})
                result = profile.create_exercises(student, diagnosis_id=body.get('diagnosis_id'), review_id=body.get('review_id'))
                return self._json(200, result)
            if path == '/api/practice/check':
                if not access.allow_model():return self._json(429,{'error':'这一分钟的请求比较多，请稍等片刻再试。','code':'MODEL_BUSY'})
                answer = _text(body.get('answer'), '答案',480)
                if body.get('exercise_id'):
                    return self._json(200, profile.submit_answer(student, _text(body['exercise_id'], '练习编号', 64), answer))
                # 旧客户端可只校验，但没有练习编号时不写入进度。
                question = _text(body.get('question'), '题目')
                ok, message = check_answer(question, answer)
                return self._json(200, {'correct': ok, 'message': message, 'saved': False})
            if path == '/api/availability':
                value = profile.set_availability(student, body.get('availability'))
                return self._json(200, {'ok': True, 'availability': value})
            if path == '/api/files/preview':
                return self._json(200, preview_pdf(body.get('file_data'), body.get('page', 1)))
            if path == '/api/learn':
                problem=_text(body.get('problem'),'题目')
                checked=prepare_lesson(problem)
                if not checked['ok']:
                    return self._json(200,{'ok':False,'message':checked['message'],'analysis':_public(checked['analysis'])})
                return self._study({**body,'problem':problem,'steps':[],
                    'recognition':{'question_type':'simplify' if '/' in problem else 'factor'}},student)
            if path == '/api/recognize':
                return self._json(200,agent.recognize(student,{'image_data':body.get('image_data')}))
            if path == '/api/chat':
                analysis = profile.diagnosis_for(student, _text(body.get('diagnosis_id'), '题目编号', 64))
                analysis['feedback']=profile.feedback_summary(student)
                try:analysis['teaching_memory']=teaching_memory.for_chat(student,analysis,body.get('question'))
                except (OSError,auth.sqlite3.Error):analysis['teaching_memory']={'records':[],'knowledge_sources':[]}
                from .source_images import for_diagnosis
                image=for_diagnosis(student,body.get('diagnosis_id'))
                if image:analysis['_source_image']=image
                tutor=junior.chat if image or analysis.get('engine')=='junior' else ai.tutor
                result = tutor(analysis, body.get('question'), body.get('level', 1), body.get('history'))
                if image:for_diagnosis(student,body.get('diagnosis_id'))
                return self._json(200, result)
            if path == '/api/speech':
                return self._json(200,speech.handle(body))
            return self._json(404, {'error': '没有找到这个接口'})
        except auth.AuthError as error:
            return self._json(error.status, {'error':str(error),'code':error.code})
        except auth.sqlite3.Error:
            return self._json(503, {'error':'账号服务暂不可用，请稍后重试。','code':'AUTH_UNAVAILABLE'})
        except DomainError as error:
            result={'error':str(error),'code':error.code}
            if error.current_revision is not None:result['current_revision']=error.current_revision
            return self._json(error.status,result)
        except contract.ContractError as error:
            return self._json(400,{'error':str(error),'code':'INVALID_INPUT'})
        except ConfirmationError as error:
            return self._json(error.status, {'error': str(error), 'code': error.code})
        except ai.ModelError as error:
            return self._json(error.status, {'error': str(error), 'code': error.code})
        except (ValueError, TypeError, UnicodeDecodeError) as error:
            return self._json(400, {'error': str(error) or '请求格式不对'})
        except OSError:
            return self._json(503, {'error': '学习记录暂时无法保存，请稍后重试', 'code': 'STORAGE_FAILED'})

    def _diagnose(self, body, student):
        problem = _text(body.get('problem'), '题目')
        steps = body.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            raise ValueError(f'作答步骤需要 1 到 {MAX_STEPS} 行')
        steps = [_text(item, '每行作答') for item in steps]
        request_id = body.get('request_id')
        if request_id is not None:
            request_id = _text(request_id, '请求编号', 64)
        result = diagnose(problem, steps)
        if not result['ok']:
            return self._json(200, {'ok': False, 'message': result['message'], 'analysis': _public(result['analysis'])})
        return self._study({**body,'problem':problem,'steps':steps,
                            'recognition':{'question_type':'simplify' if '/' in problem else 'factor'}},student)

    def _study(self,body,student):
        rid=body.get('request_id') or new_id()
        _text(rid,'请求编号',64)
        result=agent.invoke(student,'study',body,rid,strict=False)
        response={'ok':True,**result['output']}
        if not body.get('confirmed_reading_id'):response['legacy_confirmation']=True
        return self._json(200,response)



def _public(analysis):
    return cards.public_analysis(analysis)


def serve(host='127.0.0.1', port=8000):
    if os.environ.get('MYTREE_REQUIRE_AUTH')=='1' and not auth.enabled() and not access.enabled():raise RuntimeError('上线服务缺少认证配置，未启动。')
    if auth.enabled():auth._secret()
    httpd = MyTreeHTTPServer((host, port), Handler)
    print(f'小树同学：http://{host}:{port}', flush=True)
    httpd.serve_forever()


if __name__ == '__main__':
    serve(os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8000')))
