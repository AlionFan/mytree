"""Password-gated parent mode for the current account, with separate short sessions."""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from . import auth

COOKIE='mytree_parent'
TTL=15*60
_slots=threading.BoundedSemaphore(2)


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS parent_codes(email TEXT NOT NULL,purpose TEXT NOT NULL,digest TEXT NOT NULL,nonce TEXT NOT NULL,expires REAL NOT NULL,issued REAL NOT NULL,attempts INTEGER NOT NULL,sent INTEGER NOT NULL,PRIMARY KEY(email,purpose))')
    db.execute('CREATE TABLE IF NOT EXISTS parent_passwords(email TEXT PRIMARY KEY,salt TEXT NOT NULL,digest TEXT NOT NULL,version INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS parent_mode_sessions(digest TEXT PRIMARY KEY,email TEXT NOT NULL,base_digest TEXT NOT NULL,version INTEGER NOT NULL,expires REAL NOT NULL)')


def _email(account):
    if not account or not account.get('email'):raise auth.AuthError('请先通过邮箱登录。','AUTH_REQUIRED',401)
    return account['email']


def _identity(account,header):
    _email(account);actual=auth.session(header)
    if not actual or actual['email']!=account['email'] or actual['profile_id']!=account['profile_id']:raise auth.AuthError('请重新登录账号。','AUTH_REQUIRED',401)


def _base(header):
    token=auth.cookie_token(header)
    if not token:raise auth.AuthError('请重新登录账号。','AUTH_REQUIRED',401)
    return hashlib.sha256(token.encode()).hexdigest()


def _password(value):
    if not isinstance(value,str) or not 8<=len(value)<=128 or not value.strip():raise auth.AuthError('家长密码请使用8～128位字符。','PARENT_PASSWORD_FORMAT')
    try:value.encode('utf-8')
    except UnicodeError:raise auth.AuthError('家长密码含无效字符，请重新输入。','PARENT_PASSWORD_FORMAT') from None
    return value


def _hash(value,salt):
    return hashlib.scrypt(value.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=3,maxmem=64*1024*1024).hex()


def cookie(token='',clear=False):
    secure='; Secure' if os.environ.get('MYTREE_COOKIE_SECURE','1')=='1' else ''
    return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else TTL}{secure}'


def _admit(email,ip,kind):
    now=time.time();ids=[];error=None
    with auth._db() as db:
        db.execute('DELETE FROM rates WHERE at<?',(now-86400,))
        buckets=[(auth._digest('parent:'+kind+':email:'+email),5),(auth._digest('parent:'+kind+':ip:'+ip),40),(auth._digest('parent:'+kind+':global'),200)]
        if any(not auth._limit(db,b,now,600,n) for b,n in buckets):error=auth.AuthError('尝试次数较多，请十分钟后再试。','PARENT_RATE_LIMIT',429)
        else:
            for b,_ in buckets:ids.append(db.execute('INSERT INTO rates VALUES(?,?)',(b,now)).lastrowid)
    if error:raise error
    return ids


def _forgive(ids):
    with auth._db() as db:
        for identity in ids:db.execute('DELETE FROM rates WHERE rowid=?',(identity,))


def status(account,header):
    _identity(account,header);email=_email(account);base=_base(header);token=auth.cookie_token(header,COOKIE);now=time.time()
    with auth._db() as db:
        _schema(db);db.execute('DELETE FROM parent_mode_sessions WHERE expires<=?',(now,))
        pw=db.execute('SELECT version FROM parent_passwords WHERE email=?',(email,)).fetchone()
        row=db.execute('SELECT version,expires FROM parent_mode_sessions WHERE digest=? AND email=? AND base_digest=? AND expires>?',(auth._digest(token),email,base,now)).fetchone() if token else None
        unlocked=bool(pw and row and row['version']==pw['version'])
        return {'configured':bool(pw),'unlocked':unlocked,'email':email,'expires_at':row['expires'] if unlocked else None}


def require(account,header):
    if not status(account,header)['unlocked']:raise auth.AuthError('请输入家长密码后查看。','PARENT_LOCKED',403)


def lock(account,header):
    _identity(account,header);email=_email(account);base=_base(header)
    with auth._db() as db:
        _schema(db);db.execute('DELETE FROM parent_mode_sessions WHERE email=? AND base_digest=?',(email,base))
    return {'ok':True},cookie(clear=True)


def _issue(account,header,version):
    _identity(account,header);token=secrets.token_urlsafe(32);email=_email(account);base=_base(header);expires=time.time()+TTL
    with auth._db() as db:
        _schema(db)
        current=db.execute('SELECT version FROM parent_passwords WHERE email=?',(email,)).fetchone()
        if not current or current['version']!=version:raise auth.AuthError('家长密码已更新，请重新验证。','PARENT_LOCKED',403)
        db.execute('DELETE FROM parent_mode_sessions WHERE expires<=? OR (email=? AND base_digest=?)',(time.time(),email,base))
        db.execute('INSERT INTO parent_mode_sessions VALUES(?,?,?,?,?)',(auth._digest(token),email,base,version,expires))
    return {'ok':True,'expires_at':expires},cookie(token)


def _verification_email(code,purpose):
    if not re.fullmatch(r'[0-9]{6}',code) or purpose not in ('parent_setup','parent_reset'):raise ValueError('Invalid parent verification purpose')
    label='设置家长密码' if purpose=='parent_setup' else '重置家长密码'
    purpose_text='本验证码仅用于当前账号'+label+'，不能用于账号登录或其他操作。'
    plain='小树同学 · '+label+'\n\n你的家长验证码：'+code+'\n10分钟内有效，仅可使用一次。\n'+purpose_text+'\n请勿转发验证码；如非本人操作，请忽略本邮件。'
    html=f'''<!doctype html><html lang="zh-CN"><body style="margin:0;background:#f3f7ee;color:#294133;font-family:Arial,sans-serif"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:36px 16px"><table role="presentation" width="480" cellspacing="0" cellpadding="0" style="width:100%;max-width:480px;background:#fff;border:1px solid #dfE7d5;border-radius:24px"><tr><td style="padding:32px"><p style="font-size:13px;color:#5d7e4d">小树同学 · 家长端</p><h1 style="font-size:25px">{label}</h1><p style="line-height:1.8;font-size:14px">请回到家长端，输入下方验证码。</p><div style="padding:22px 12px;background:#eef6e5;border-radius:16px;text-align:center;font-size:34px;font-weight:bold;letter-spacing:8px">{code}</div><p style="font-size:13px;line-height:1.8">10分钟内有效，仅可使用一次。<br>{purpose_text}</p><p style="font-size:12px;line-height:1.8;color:#7a8573">请勿向他人提供验证码。如非本人操作，请忽略本邮件。</p><a href="https://mytree.joybeat.cn/parent" style="color:#3a6a42">打开小树同学家长端</a></td></tr></table></td></tr></table></body></html>'''
    return plain,html


def _send_code(email,code,purpose):
    config=auth.smtp_settings()
    if not auth.mail_ready():raise auth.AuthError('验证码邮件服务尚未开通，请稍后重试。','MAIL_UNAVAILABLE',503)
    label='设置家长密码' if purpose=='parent_setup' else '重置家长密码'
    message=auth.EmailMessage();message['From']=auth.formataddr(('小树同学',config['from']));message['To']=email;message['Subject']='小树同学 · '+label
    plain,html=_verification_email(code,purpose)
    message.set_content(plain);message.add_alternative(html,subtype='html')
    try:
        with auth.smtplib.SMTP_SSL(config['host'],int(config.get('port',465)),timeout=15,context=auth.ssl.create_default_context()) as client:
            client.login(config['user'],config['password'])
            if client.send_message(message):raise auth.smtplib.SMTPException('recipient refused')
    except (OSError,auth.smtplib.SMTPException,ValueError):raise auth.AuthError('验证码邮件发送失败，请稍后重试。','MAIL_SEND_FAILED',503) from None


def request_code(account,header,purpose,ip):
    _identity(account,header);email=_email(account)
    if purpose not in ('parent_setup','parent_reset'):raise auth.AuthError('验证码用途不正确。')
    now=time.time();code=f'{secrets.randbelow(1000000):06d}';nonce=secrets.token_hex(16)
    with auth._db() as db:
        _schema(db);pw=db.execute('SELECT 1 FROM parent_passwords WHERE email=?',(email,)).fetchone()
        if purpose=='parent_setup' and pw:raise auth.AuthError('家长密码已设置，请输入密码。','PARENT_ALREADY_CONFIGURED',409)
        if purpose=='parent_reset' and not pw:raise auth.AuthError('请先设置家长密码。','PARENT_NOT_CONFIGURED',409)
        old=db.execute('SELECT issued FROM parent_codes WHERE email=? AND purpose=?',(email,purpose)).fetchone()
        if old and now-old['issued']<60:raise auth.AuthError('请60秒后再获取验证码。','PARENT_RATE_LIMIT',429)
        buckets=[(auth._digest('parent-mail:email:'+email),86400,10),(auth._digest('parent-mail:ip:'+ip),3600,20),(auth._digest('parent-mail:global'),3600,100)]
        if any(not auth._limit(db,b,now,w,n) for b,w,n in buckets):raise auth.AuthError('验证码发送较多，请稍后再试。','PARENT_RATE_LIMIT',429)
        for b,_,_ in buckets:db.execute('INSERT INTO rates VALUES(?,?)',(b,now))
        db.execute('INSERT OR REPLACE INTO parent_codes VALUES(?,?,?,?,?,?,0,0)',(email,purpose,auth._digest(email+':'+purpose+':'+nonce+':'+code),nonce,now+600,now))
    try:_send_code(email,code,purpose)
    except BaseException:
        with auth._db() as db:db.execute('DELETE FROM parent_codes WHERE email=? AND purpose=? AND nonce=?',(email,purpose,nonce))
        raise
    with auth._db() as db:db.execute('UPDATE parent_codes SET sent=1 WHERE email=? AND purpose=? AND nonce=?',(email,purpose,nonce))
    return {'ok':True,'retry_after':60,'expires_in':600,'message':'验证码已发送到当前账号邮箱，仅用于'+('设置' if purpose=='parent_setup' else '重置')+'家长密码。'}


def _store_password(email,action,code,salt,digest):
    if not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code):raise auth.AuthError('请输入邮件中的6位家长验证码。')
    purpose='parent_setup' if action=='setup' else 'parent_reset';error=None;version=None;now=time.time()
    with auth._db() as db:
        _schema(db);current=db.execute('SELECT version FROM parent_passwords WHERE email=?',(email,)).fetchone()
        row=db.execute('SELECT * FROM parent_codes WHERE email=? AND purpose=?',(email,purpose)).fetchone()
        if action=='setup' and current:error=auth.AuthError('家长密码已设置，请重新验证。','PARENT_ALREADY_CONFIGURED',409)
        elif action=='reset' and not current:error=auth.AuthError('请先设置家长密码。','PARENT_NOT_CONFIGURED',409)
        elif not row or not row['sent'] or row['expires']<=now or row['attempts']>=5:error=auth.AuthError('家长验证码无效、已用或已过期，请重新获取。','PARENT_CODE_INVALID')
        elif not hmac.compare_digest(row['digest'],auth._digest(email+':'+purpose+':'+row['nonce']+':'+code)):
            db.execute('UPDATE parent_codes SET attempts=attempts+1 WHERE email=? AND purpose=?',(email,purpose));error=auth.AuthError('家长验证码不正确，请检查后重试。','PARENT_CODE_INVALID')
        else:
            version=(current['version'] if current else 0)+1
            db.execute('INSERT INTO parent_passwords VALUES(?,?,?,?) ON CONFLICT(email) DO UPDATE SET salt=excluded.salt,digest=excluded.digest,version=excluded.version',(email,salt,digest,version))
            db.execute('DELETE FROM parent_codes WHERE email=?',(email,))
            db.execute('DELETE FROM parent_mode_sessions WHERE email=?',(email,))
    if error:raise error
    return version


def handle(account,header,action,body,ip):
    _identity(account,header);email=_email(account)
    if action=='lock':return lock(account,header)
    if action=='send-code':
        if set(body)!={'purpose'}:raise auth.AuthError('验证码请求字段不正确。')
        return request_code(account,header,body['purpose'],ip),None
    if action not in ('setup','unlock','reset'):raise auth.AuthError('邀请配对已停用，请使用同一账号的家长端。','PARENT_LEGACY_DISABLED',410)
    allowed={'password'} if action=='unlock' else {'password','confirm_password','code'}
    if set(body)-allowed:raise auth.AuthError('请求含不支持的字段。')
    password=_password(body.get('password'))
    if action!='unlock' and password!=body.get('confirm_password'):raise auth.AuthError('两次家长密码不一致。','PARENT_PASSWORD_MISMATCH')
    if not _slots.acquire(blocking=False):raise auth.AuthError('正在验证，请稍后重试。','PARENT_BUSY',429)
    try:
        ids=_admit(email,ip,'unlock' if action=='unlock' else 'setup')
        with auth._db() as db:_schema(db);row=db.execute('SELECT * FROM parent_passwords WHERE email=?',(email,)).fetchone()
        if action=='unlock':
            actual=_hash(password,row['salt'] if row else '0'*32)
            if not row or not hmac.compare_digest(actual,row['digest']):raise auth.AuthError('家长密码不正确，请重新输入。','PARENT_PASSWORD_INVALID',403)
            result=_issue(account,header,row['version'])
        else:
            salt=secrets.token_hex(16);digest=_hash(password,salt)
            version=_store_password(email,action,body.get('code'),salt,digest)
            result=_issue(account,header,version)
        _forgive(ids);return result
    finally:_slots.release()
