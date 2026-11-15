#!/usr/bin/env python3
"""Configure official AI privately, or probe configured APIs with synthetic data."""
import argparse
import base64
import getpass
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request
import urllib.parse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import ai


def profile_values(key, base, tutor_key=None, tutor_model='qwen3.6-flash', vision_model='qwen3.6-flash'):
    ai.validate_base(base)
    host=urllib.parse.urlparse(base).hostname
    if host not in ('dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com') and not (host.endswith('.maas.aliyuncs.com')):
        raise ValueError('请使用百炼官方地域或业务空间地址。')
    if not base.endswith('/compatible-mode/v1'):
        raise ValueError('百炼地址应以 /compatible-mode/v1 结尾。')
    native=base.removesuffix('/compatible-mode/v1')+'/api/v1'
    values={'MYTREE_ENABLE_THINKING':'false','MYTREE_MODEL_TIMEOUT':'45'}
    for role in ('VISION','TUTOR','DIAGRAM','ASR','TTS','EMBEDDING'):
        values['MYTREE_'+role+'_API_BASE']=native if role=='TTS' else base
        values['MYTREE_'+role+'_API_KEY']=key
    values.update(MYTREE_VISION_MODEL=vision_model,MYTREE_TUTOR_MODEL=tutor_model,
                  MYTREE_DIAGRAM_MODEL=tutor_model,MYTREE_ASR_MODEL='qwen3-asr-flash',
                  MYTREE_TTS_MODEL='qwen3-tts-flash',MYTREE_TTS_VOICE='Cherry',
                  MYTREE_ASR_PROTOCOL='qwen',MYTREE_TTS_PROTOCOL='qwen',
                  MYTREE_EMBEDDING_MODEL='text-embedding-v4',MYTREE_EMBEDDING_DIMS='1024')
    if tutor_key is not None:
        for role in ('TUTOR','DIAGRAM'):
            values['MYTREE_'+role+'_API_BASE']='https://api.deepseek.com'
            values['MYTREE_'+role+'_API_KEY']=tutor_key
    return values


def write_private(path, values):
    previous=path.read_text() if path.exists() else ''
    lines=[line for line in previous.splitlines() if line.split('=',1)[0].strip() not in values]
    content='\n'.join(lines+['']+[f'{k}={v}' for k,v in values.items()])+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.official-ai-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as out:out.write(content)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def check():
    from app import speech
    from PIL import Image
    cfg=ai.settings()
    # Only public synthetic text/image/audio; no student records are read.
    out=io.BytesIO();Image.new('RGB',(64,64),'white').save(out,format='PNG')
    picture='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
    failures=[]
    for role in ('vision','tutor','diagram','tts','asr','embedding'):
        started=time.monotonic()
        try:
            if role in ('vision','tutor','diagram'):
                content=[{'type':'text','text':'Return JSON {"ok":true}.'},{'type':'image_url','image_url':{'url':picture}}] if role=='vision' else 'Return JSON {"ok":true}.'
                result,_=ai.complete(role,[{'role':'user','content':content}],cfg,limit=100)
                if result.get('ok') is not True:raise ValueError()
            elif role=='tts':
                audio=speech.handle({'action':'speak','text':'Hello, this is a connection test.'})['audio_data']
            elif role=='asr':
                if not locals().get('audio'):raise ValueError()
                speech.handle({'action':'transcribe','audio_data':audio})
            else:
                base,key=ai.endpoint(cfg,'embedding')
                if not key:raise ai.ModelError('未配置','MODEL_NOT_CONFIGURED')
                request=urllib.request.Request(base+'/embeddings',data=json.dumps({'model':cfg.embedding_model,'input':['Synthetic connection test.'],'dimensions':cfg.embedding_dims}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
                with urllib.request.urlopen(request,timeout=cfg.timeout) as response:raw=response.read(200_001)
                if len(raw)>200_000 or len(json.loads(raw)['data'][0]['embedding'])!=cfg.embedding_dims:raise ValueError()
            print(f'{role}: OK ({time.monotonic()-started:.2f}s)')
        except Exception as error:
            code=error.code if isinstance(error,ai.ModelError) else 'CHECK_FAILED'
            print(f'{role}: {code} ({time.monotonic()-started:.2f}s)')
            failures.append(role)
    return bool(failures)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Make real, billable synthetic API probes; do not print keys or responses.')
    parser.add_argument('--base',default='https://dashscope.aliyuncs.com/compatible-mode/v1',help='Official regional/workspace compatible-mode base URL.')
    parser.add_argument('--deepseek',action='store_true',help='Use DeepSeek for text and diagram generation.')
    parser.add_argument('--vision-model',default='qwen3.6-flash')
    parser.add_argument('--tutor-model',default=None)
    args=parser.parse_args()
    if args.check:return check()
    for name in (args.vision_model,args.tutor_model):
        if name is not None and (not name or not all(c.isalnum() or c in '._-' for c in name)):
            parser.error('模型ID格式不正确。')
    ai.validate_base(args.base)
    print('API Key仅隐藏输入并保存到服务端 .env.local；本步骤不调用API。请使用与地址地域一致的百炼Key。')
    key=getpass.getpass('百炼 API Key：').strip()
    deepseek=getpass.getpass('DeepSeek 官方 API Key：').strip() if args.deepseek else None
    for secret in (key,deepseek):
        if secret is not None and (not secret or len(secret)>512 or any(c.isspace() for c in secret)):
            raise SystemExit('密钥格式不正确，未保存。')
    values=profile_values(key,args.base,deepseek,args.tutor_model or ('deepseek-flash' if args.deepseek else 'qwen3.6-flash'),args.vision_model)
    write_private(ai.CONFIG_PATH,values)
    print('已保存私有配置（0600），其余邮箱/账号等配置保留。未发布线上。')
    print('下一步用同一Python运行本脚本 --check，执行真实API联通与耗时检查。环境变量优先于此文件。')
    return 0


if __name__=='__main__':sys.exit(main())
