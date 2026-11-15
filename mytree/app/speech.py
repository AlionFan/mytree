"""Bounded official Qwen and OpenAI-compatible ASR/TTS; audio stays in request memory only."""
import base64
import binascii
import json
import io
import math
import wave
import re
import socket
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid
from . import ai

_AUDIO=re.compile(r'^data:audio/(webm|mp4|m4a|ogg|mpeg|mp3|wav)(?:;codecs=[A-Za-z0-9.,-]+)?;base64,([A-Za-z0-9+/=]+)$')


def audio_bytes(value):
    if not isinstance(value,str) or len(value)>2_800_000:raise ValueError('录音过长，请控制在20秒以内。')
    match=_AUDIO.fullmatch(value)
    if not match:raise ValueError('录音格式暂不支持，请重新录制。')
    try:data=base64.b64decode(match[2],validate=True)
    except binascii.Error:raise ValueError('录音内容损坏，请重新录制。') from None
    kind=match[1]
    valid=(kind=='wav' and data[:4]==b'RIFF' and data[8:12]==b'WAVE' or
           kind=='webm' and data[:4]==b'\x1aE\xdf\xa3' or kind=='ogg' and data[:4]==b'OggS' or
           kind in ('mp4','m4a') and data[4:8]==b'ftyp' or kind in ('mp3','mpeg') and (data[:3]==b'ID3' or data[:1]==b'\xff'))
    if not valid or not 16<=len(data)<=2_000_000:raise ValueError('没有读到有效录音，请重新录制。')
    return data,'mp3' if kind=='mpeg' else 'mp4' if kind=='m4a' else kind


def validate_wav(raw):
    """Reject empty/too-short/silent PCM locally before a billable ASR request."""
    try:
        with wave.open(io.BytesIO(raw),'rb') as recording:
            channels,width,rate,count=recording.getnchannels(),recording.getsampwidth(),recording.getframerate(),recording.getnframes()
            if channels not in (1,2) or width not in (1,2,3,4) or not rate:raise ValueError()
            samples=recording.readframes(count)
            block=channels*width
            if len(samples)%block:raise ValueError()
            if len(samples)!=count*block:
                # Some model TTS streams use near-2GB/4GB RIFF/data size placeholders.
                # Use received complete PCM frames only for this recognizable case.
                offset=12;declared_data=None
                while offset+8<=len(raw):
                    tag=raw[offset:offset+4];size=int.from_bytes(raw[offset+4:offset+8],'little')
                    if tag==b'data':declared_data=size;break
                    offset+=8+size+(size%2)
                markers=(int.from_bytes(raw[4:8],'little'),declared_data)
                if markers not in ((0x7fffffbf,0x7fffff9b),(0xffffffff,0xffffffff)):raise ValueError()
                count=len(samples)//block
            duration=count/rate
    except (wave.Error,EOFError,ValueError):
        raise ValueError('这次录音没有保存完整，请重新录制；也可以输入文字提问。') from None
    if duration<.35:raise ValueError('录音太短，请点“语音提问”，说完一句话后再点“结束并提问”。')
    if duration>21:raise ValueError('录音较长，请每次说一句话，控制在20秒以内。')
    scale=float(1<<(width*8-1))
    peak=energy=0.0
    for i in range(0,len(samples),width):
        value=(samples[i]-128)/128 if width==1 else int.from_bytes(samples[i:i+width],'little',signed=True)/scale
        peak=max(peak,abs(value));energy+=value*value
    rms=math.sqrt(energy/max(1,count*channels))
    if peak<.003 and rms<.0006:
        raise ai.ModelError('没有检测到麦克风声音。请检查麦克风是否静音、选对输入设备后重录；也可以输入文字提问。','SPEECH_NO_AUDIO',422)


def transcription_text(data, qwen=False):
    try:
        result=json.loads(data)
        text=result['choices'][0]['message']['content'] if qwen else result['text']
        if not isinstance(text,str):raise ValueError()
    except (ValueError,TypeError,KeyError,IndexError):
        raise ai.ModelError('这次没有收到识别文字，请重新录制一句话；也可以输入文字提问。','SPEECH_RESPONSE_INVALID') from None
    if not text.strip():
        raise ai.ModelError('没有听到完整的话。请靠近麦克风，说完一句话后再结束录音；也可以输入文字提问。','SPEECH_NOT_HEARD',422)
    if len(text)>800:raise ai.ModelError('这段话较长，请分成短句重新提问。','SPEECH_TEXT_TOO_LONG',422)
    return text.strip()


def _request(action,body,content_type,model,cfg,path=None):
    base,key=ai.endpoint(cfg,'asr' if action=='transcriptions' else 'tts')
    if not key or not model:raise ai.ModelError('语音服务尚未配置。','SPEECH_NOT_CONFIGURED',503)
    if not ai._slots.acquire(blocking=False):raise ai.ModelError('服务正在处理上一段内容，请稍后再试。','MODEL_BUSY',429)
    start=time.monotonic();code='FAILED'
    try:
        req=urllib.request.Request(base+(path or '/audio/'+action),data=body,headers={'Content-Type':content_type,'Authorization':'Bearer '+key,'User-Agent':'MyTree/0.4'})
        with urllib.request.urlopen(req,timeout=cfg.timeout) as response:
            data=response.read(3_000_001);mime=response.headers.get_content_type()
        if len(data)>3_000_000:raise ai.ModelError('语音结果过长，请用短句再试。','MODEL_OUTPUT_INVALID')
        code='OK';return data,mime
    except urllib.error.HTTPError as error:
        status=error.code;error.close();code='HTTP_'+str(status)
        if status in (401,403):raise ai.ModelError('语音服务的密钥暂不可用，请联系维护者更新。','MODEL_AUTH',503) from None
        if status==429:raise ai.ModelError('语音服务繁忙，请稍后重试。','MODEL_BUSY',429) from None
        raise ai.ModelError('语音服务暂未返回结果，请重试。','MODEL_UPSTREAM',502) from None
    except (socket.timeout,TimeoutError):raise ai.ModelError('语音处理等待较久，可以重试。','MODEL_TIMEOUT',504) from None
    except (urllib.error.URLError,OSError):raise ai.ModelError('暂时连不上语音服务，请稍后重试。','MODEL_UPSTREAM',502) from None
    finally:
        ai._slots.release();ai._log('speech_'+action,model,time.monotonic()-start,{},code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _qwen_audio(data, cfg):
    """Fetch only Qwen's signed result host, without API credentials/redirects."""
    try:
        result=json.loads(data)
        if result.get('code') or result.get('status_code',200)!=200:raise ValueError()
        audio=result['output']['audio']
        if audio.get('data'):
            raw=base64.b64decode(audio['data'],validate=True)
        else:
            url=urllib.parse.urlparse(audio['url'])
            host=url.hostname or ''
            if url.scheme not in ('http','https') or url.username or url.password or url.port not in (None,443) or not re.fullmatch(r'dashscope-result-[a-z0-9-]+\.oss[a-z0-9-]*\.aliyuncs\.com',host):raise ValueError()
            # Official examples may return HTTP signed OSS URLs. Always use TLS.
            secure=urllib.parse.urlunparse(url._replace(scheme='https'))
            with urllib.request.build_opener(_NoRedirect()).open(secure,timeout=cfg.timeout) as response:
                raw=response.read(3_000_001)
        if not 16<=len(raw)<=3_000_000:raise ValueError()
        return raw
    except (ValueError,TypeError,KeyError,AttributeError,urllib.error.URLError,OSError):
        raise ai.ModelError('语音结果无法播放，请重试。','MODEL_OUTPUT_INVALID') from None


def handle(body):
    cfg=ai.settings();action=body.get('action')
    if action=='transcribe':
        if set(body)-{'student','action','audio_data'}:raise ValueError('录音请求含不支持的字段。')
        raw,kind=audio_bytes(body.get('audio_data'))
        if kind=='wav':validate_wav(raw)
        boundary='MyTree'+uuid.uuid4().hex
        if cfg.asr_protocol=='qwen':
            payload={'model':cfg.asr,'messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':body['audio_data']}}]}],'stream':False}
            data,_=_request('transcriptions',json.dumps(payload).encode(),'application/json',cfg.asr,cfg,'/chat/completions')
            return {'ok':True,'text':transcription_text(data,qwen=True),'model':cfg.asr}
        fields=b''
        for key,value in (('model',cfg.asr),('response_format','json')):
            fields+=(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
        fields+=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="recording.{kind}"\r\nContent-Type: audio/{kind}\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
        data,_=_request('transcriptions',fields,'multipart/form-data; boundary='+boundary,cfg.asr,cfg)
        return {'ok':True,'text':transcription_text(data),'model':cfg.asr}
    if action=='speak':
        if set(body)-{'student','action','text'}:raise ValueError('朗读请求含不支持的字段。')
        text=body.get('text')
        if not isinstance(text,str) or not text.strip() or len(text)>1200:raise ValueError('请将朗读内容控制在1200字符以内。')
        language='zh' if re.search(r'[\u3400-\u9fff]',text) else 'en'
        if cfg.tts_protocol=='qwen':
            if len(text)>600:raise ValueError('请将本次朗读控制在600字符以内。')
            payload={'model':cfg.tts,'input':{'text':text,'voice':cfg.voice,'language_type':'Chinese' if language=='zh' else 'English'}}
            data,_=_request('speech',json.dumps(payload).encode(),'application/json',cfg.tts,cfg,'/services/aigc/multimodal-generation/generation')
            data=_qwen_audio(data,cfg)
            return _audio_result(data,'audio/wav',cfg,language)
        payload={'model':cfg.tts,'input':text,'voice':cfg.voice,'response_format':'mp3'}
        if not cfg.tts.startswith('qwen3-tts'):payload['speed']=.95
        payload=json.dumps(payload).encode()
        data,mime=_request('speech',payload,'application/json',cfg.tts,cfg)
        return _audio_result(data,mime,cfg,language)
    raise ValueError('语音操作需要是转录或朗读。')


def _audio_result(data,mime,cfg,language='en'):
    if not (mime.startswith('audio/') or mime=='application/octet-stream') or len(data)<16:raise ai.ModelError('语音结果无法播放，请重试。','MODEL_OUTPUT_INVALID')
    audio_type='audio/wav' if data[:4]==b'RIFF' and data[8:12]==b'WAVE' else 'audio/ogg' if data[:4]==b'OggS' else 'audio/mpeg' if data[:3]==b'ID3' or data[:1]==b'\xff' else None
    if audio_type is None:raise ai.ModelError('语音结果无法播放，请重试。','MODEL_OUTPUT_INVALID')
    return {'ok':True,'audio_data':'data:'+audio_type+';base64,'+base64.b64encode(data).decode(),'language':language,'model':cfg.tts,'synthetic':True}
