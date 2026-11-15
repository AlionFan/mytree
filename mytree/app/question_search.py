"""Optional official-bank lookup. Never changes OCR, answers or learning state."""
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
import base64
import copy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import contract
from .errors import DomainError
from .reading_registry import registry

ENDPOINT='https://openapi.youdao.com/ocrquestionapi'
SOURCE='https://ai.youdao.com/DOCSIRMA/html/learn/api/jptk/index.html'
PRIVATE=Path(__file__).resolve().parents[1]/'data/deployment/questionbank.json'
_LOCK=threading.RLock()
_CACHE=OrderedDict()
TTL=600


def settings():
    try:
        path=Path(os.environ.get('MYTREE_QUESTIONBANK_CONFIG',str(PRIVATE)))
        data=json.loads(path.read_text()) if path.exists() else {}
        key=os.environ.get('MYTREE_YOUDAO_APP_KEY',data.get('app_key',''))
        secret=os.environ.get('MYTREE_YOUDAO_APP_SECRET',data.get('app_secret',''))
        limit=int(os.environ.get('MYTREE_QUESTIONBANK_DAILY_LIMIT',data.get('daily_limit',20)))
        if not all(isinstance(x,str) and len(x)<=256 and not any(c.isspace() for c in x) for x in (key,secret)):raise ValueError()
        if not 1<=limit<=1000:raise ValueError()
        return key,secret,limit
    except (OSError,ValueError,TypeError,AttributeError):
        raise DomainError('QUESTIONBANK_CONFIG_INVALID','题库配置暂不可用，请联系管理员。',503) from None


def capabilities():
    try:
        key,secret,_=settings()
        return 'configured' if key and secret else 'not_configured'
    except DomainError:return 'unavailable'


class PlainContent(HTMLParser):
    """Provider markup is data. Return plain text and explicit unexpanded-image markers."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.images=[];self.hidden=0;self.has_image=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','iframe','object','svg','math'):
            if tag in ('object','svg','math'):self.has_image=True
            self.hidden+=1;return
        if self.hidden:return
        if tag in ('p','div','br','li','tr'):self.parts.append('\n')
        if tag in ('sup','sub'):self.parts.append('^{' if tag=='sup' else '_{')
        if tag=='img':
            self.has_image=True
            self.parts.append('\n[题库图片]\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','iframe','object','svg','math'):
            self.hidden=max(0,self.hidden-1)
        if not self.hidden and tag in ('p','div','li','tr'):self.parts.append('\n')
        if not self.hidden and tag in ('sup','sub'):self.parts.append('}')
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def plain(value):
    if not isinstance(value,str) or len(value)>10000:raise ValueError()
    parser=PlainContent();parser.feed(value);parser.close()
    text=re.sub(r'\n{3,}','\n\n',''.join(parser.parts)).strip()
    if len(text)>10000:raise ValueError()
    return {'text':text,'images':parser.images,'has_images':parser.has_image}


def comparable(text):
    for mark in ('$',r'\(',r'\)',r'\[',r'\]'):text=text.replace(mark,'')
    return re.sub(r'\s+','',text).replace('−','-').replace('²','^2').replace('³','^3')


def query_text(reading):
    # Exact stem only; never truncate, append a student step or send the source photo.
    from .page_reading import _transcript_key
    text=reading['problem'].strip()
    fragments=''.join(_transcript_key(item['text'],reading.get('printed_number',''),True) for item in reading.get('fragments',[]) if item['role']=='problem')
    if not fragments or fragments!=_transcript_key(text,reading.get('printed_number',''),True) or (reading.get('problem_latex') and _transcript_key(reading['problem_latex'],reading.get('printed_number',''),True)!=_transcript_key(text,reading.get('printed_number',''),True)):
        return None,'原题片段存在不一致，请重拍这题后再查题库。'
    if 0 in reading.get('uncertain_lines',[]):
        return None,'这道题的题干还没读清，请重拍后再查题库。'
    if not text or not reading['problem_complete'] or '?' in text:
        return None,'这道题的题干还没读完整，请先重拍这题。'
    if not reading['diagram_complete'] or reading.get('diagram_description') or re.search('如图|下图|图中|如表|表中',text):
        return None,'这题需要图表；当前文字题库查询不能核对完整图表，原题保留。'
    if len(text)>=50:
        return None,'这题超过题库文字查询的长度限制，暂不检索；不会截掉条件。'
    return text,None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def provider_query(text,key,secret):
    # Official q field is Base64, including searchType=text; live account test pending.
    q=base64.b64encode(text.encode('utf-8')).decode('ascii')
    salt=uuid.uuid4().hex;stamp=str(int(time.time()))
    short=q if len(q)<=20 else q[:10]+str(len(q))+q[-10:]
    sign=hashlib.sha256((key+short+salt+stamp+secret).encode()).hexdigest()
    payload=urllib.parse.urlencode({'q':q,'appKey':key,'salt':salt,'curtime':stamp,'sign':sign,'signType':'v2','type':'1','searchType':'text'}).encode()
    request=urllib.request.Request(ENDPOINT,data=payload,headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=12) as response:
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError()
        result=json.loads(raw)
        if not isinstance(result,dict) or not isinstance(result.get('errorCode'),(str,int)):raise ValueError()
        code=str(result['errorCode'])
        if code!='0':
            message='题库服务暂不可用，请稍后重试。'
            if code in ('108','110','111','112','202'):message='题库应用尚未开通或配置无效，请联系管理员。'
            elif code=='401':message='题库服务余额不足，请联系管理员。'
            elif code in ('411','412','1411'):message='题库查询较多，请稍后再试。'
            raise DomainError('QUESTIONBANK_UPSTREAM_FAILED',message,503)
        return result
    except DomainError:raise
    except (OSError,ValueError,TypeError,urllib.error.HTTPError,urllib.error.URLError):
        raise DomainError('QUESTIONBANK_UNAVAILABLE','题库暂时没有响应，原题和学习内容已保留。',503) from None


def candidates(result,reading):
    data=result.get('data')
    values=data.get('questions') if isinstance(data,dict) else None
    if not isinstance(values,list):raise DomainError('QUESTIONBANK_INVALID_OUTPUT','题库结果不完整，请稍后重试。',503)
    output=[];seen=set()
    for value in values[:20]:
        try:
            if not isinstance(value,dict):continue
            source_id=value.get('id')
            if not isinstance(source_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',source_id) or source_id in seen:continue
            content=plain(value.get('content'))
            if not content['text']:continue
            comparison='incomplete_or_unchecked' if content['has_images'] else 'text_equal' if comparable(content['text'])==comparable(reading['problem']) else 'different'
            output.append({'candidate_id':hashlib.sha256(source_id.encode()).hexdigest()[:24],'provider_item_id':source_id,'provider':'youdao','provider_name':'有道精品题库','source_url':None,'content':content,'comparison':comparison,'verified':False})
            seen.add(source_id)
            if len(output)==5:break
        except (TypeError,ValueError):continue
    if values and not output:raise DomainError('QUESTIONBANK_INVALID_OUTPUT','题库候选缺少可追溯内容，请稍后重试。',503)
    return output


def reserve(student,limit):
    """Persistent daily ceiling survives server restart; reserve even on timeout."""
    path=Path(os.environ.get('MYTREE_QUESTIONBANK_DB',str(PRIVATE.parent.parent/'questionbank.sqlite3')))
    day=datetime.now(timezone(timedelta(hours=8))).date().isoformat();now=time.time()
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path,timeout=5) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS calls (day TEXT, at REAL, owner TEXT)')
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM calls WHERE day < ?', (day,))
            count=conn.execute('SELECT count(*) FROM calls WHERE day=?',(day,)).fetchone()[0]
            owner=hashlib.sha256(student.encode()).hexdigest()
            recent=conn.execute('SELECT count(*) FROM calls WHERE owner=? AND at>?',(owner,now-60)).fetchone()[0]
            if count>=limit:raise DomainError('QUESTIONBANK_DAILY_LIMIT','今天的题库查询次数已用完，原学习功能可继续使用。',429)
            if recent>=6:raise DomainError('QUESTIONBANK_BUSY','题库查询较多，请稍后再试。',429)
            conn.execute('INSERT INTO calls VALUES (?,?,?)',(day,now,owner))
    except DomainError:raise
    except (OSError,sqlite3.Error):raise DomainError('QUESTIONBANK_UNAVAILABLE','题库查询计数暂不可用，请稍后重试。',503) from None


def _search(student,body):
    contract.definition('QuestionSearchInput',body)
    reading=registry.page_reading(student,body['batch_id'],body['reading_id'],body['source_revision'])
    base={'provider':'youdao','status':'not_configured','candidates':[],'cached':False,'reading_id':body['reading_id'],'source_revision':body['source_revision'],'source':{'batch_id':body['batch_id'],'reading_id':body['reading_id'],'source_revision':body['source_revision']},'query_id':uuid.uuid4().hex,'queried_at':datetime.now(timezone.utc).isoformat()}
    key,secret,limit=settings()
    if not key or not secret:return {**base,'message':'题库尚未开通，当前可继续使用照片识别和学习。'}
    text,message=query_text(reading)
    if message:return {**base,'status':'unsupported','message':message}
    cache_key=hashlib.sha256(json.dumps([student,body['batch_id'],body['reading_id'],body['source_revision'],text,key,hashlib.sha256(secret.encode()).hexdigest()],ensure_ascii=False).encode()).hexdigest()
    # Single flight includes outbound call. No second charge on rapid repeated clicks.
    with _LOCK:
        hit=_CACHE.get(cache_key)
        if hit and time.monotonic()-hit[0]<TTL:return {**copy.deepcopy(hit[1]),'cached':True}
        reserve(student,limit)
        result=provider_query(text,key,secret)
        found=candidates(result,reading)
        output={**base,'status':'candidates' if found else 'no_results','candidates':found,'queried_at':datetime.now(timezone.utc).isoformat(),'message':'以下是题库候选，尚未确认是原题；照片题干和原作答保持原样。' if found else '题库没有找到候选题，仍可按照片继续学习。'}
        try:contract.definition('QuestionSearchOutput',output)
        except contract.ContractError:
            raise DomainError('QUESTIONBANK_INVALID_OUTPUT','题库结果没有通过检查，请稍后重试。',503) from None
        _CACHE[cache_key]=(time.monotonic(),copy.deepcopy(output));_CACHE.move_to_end(cache_key)
        while len(_CACHE)>128:_CACHE.popitem(last=False)
        return output


def search(student,body):
    return contract.definition('QuestionSearchOutput',_search(student,body))
