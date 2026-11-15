"""Shared business dispatcher and the authoritative Agent envelope adapter."""
from collections import OrderedDict
import copy
import hashlib
import json
import threading
import time

from . import ai, cards, contract, store, review, quiz, tree, growth
from .errors import DomainError
from .reading_registry import registry as readings, ConfirmationError, new_id


_read_cache = OrderedDict()
_read_lock = threading.Lock()
_STATUS = {'ALLOWANCE_EXHAUSTED':429,'INVALID_INPUT':400,'NEEDS_CONFIRMATION':409,'UNSUPPORTED':422,'MODEL_NOT_CONFIGURED':503,
           'MODEL_TIMEOUT':504,'MODEL_BUSY':429,'MODEL_UPSTREAM':502,'MODEL_OUTPUT_INVALID':502,
           'MODEL_AUTH':503,'NOT_FOUND':404,'CONFLICT':409,'STORAGE_FAILED':503}


def recognize(student, params):
    result = ai.recognize(params['image_data'])
    contract.definition('RecognizeOutput',{key:value for key,value in result.items() if key not in ('ok','meta')})
    readings.remember(student,result)
    return result


def _recognize_once(student, request_id, params):
    digest=hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    key=(student,'recognize',request_id)
    with store.request_lock(key):
        with _read_lock:
            cached=_read_cache.get(key)
            if cached and time.monotonic()-cached[0] <= 7200:
                if digest != cached[1]:
                    raise DomainError('CONFLICT','同一请求编号对应的内容已改变，请重新发起。',409)
                result=copy.deepcopy(cached[2])
                readings.remember(student,result)
                return result
        result=recognize(student,params)
        with _read_lock:
            _read_cache[key]=(time.monotonic(),digest,copy.deepcopy(result))
            _read_cache.move_to_end(key)
            while len(_read_cache)>128:_read_cache.popitem(last=False)
        return result


def invoke(student, operation, params, request_id, strict=True):
    if operation=='recognize':
        value=_recognize_once(student,request_id,params)
        return {'status':'needs_confirmation','output':{k:v for k,v in value.items() if k not in ('ok','meta')},
                'verification':{'level':'unavailable','label':'识别转录需要你对照原图确认'},'effects':[],
                'next_actions':[{'operation':'study','label':'核对后整理这道题','requires':['confirmed_reading_id']}],
                'meta':value.get('meta',{})}
    if operation=='study':return cards.study(student,params,request_id,strict=strict)
    if operation=='card.list':
        return {'status':'ok','output':cards.list_cards(student,params),'effects':[],
                'verification':{'level':'unavailable','label':'来自本机保存的学习记录'}}
    if operation=='card.edit':return cards.edit(student,params,request_id)
    if operation=='review.today':
        return {'status':'ok','output':review.today(student),'effects':[],
                'verification':{'level':'unavailable','label':'来自保存的复习安排'}}
    if operation=='review.complete':return review.complete(student,params,request_id)
    if operation=='quiz.start':return quiz.start(student,params,request_id)
    if operation=='quiz.answer':return quiz.answer(student,params,request_id)
    if operation=='card.unlock':return quiz.unlock(student,params,request_id)
    if operation=='tree.get':
        return {'status':'ok','output':tree.get(student),'effects':[],
                'verification':{'level':'unavailable','label':'本机参考目录与自己整理的知识卡'}}
    if operation=='tree.move':return tree.move(student,params,request_id)
    if operation=='growth.get':
        return {'status':'ok','output':growth.get(student,params),'effects':[],
                'verification':{'level':'unavailable','label':'参考成长分，依据去重的历史事实累计'}}
    if operation=='leaderboard.get':
        return {'status':'ok','output':growth.leaderboard(student,params),'effects':[],
                'verification':{'level':'unavailable','label':'小组未开启；个人参考成长请查看 growth.get'}}
    raise DomainError('UNSUPPORTED','这个操作尚未接通，请保留当前学习进度。',422)


def _identity(payload):
    if not isinstance(payload,dict):return new_id(),'study'
    request_id=payload.get('request_id')
    if not isinstance(request_id,str) or not 1<=len(request_id)<=64:request_id=new_id()
    operation=payload.get('operation')
    try:contract.definition('Operation',operation)
    except contract.ContractError:operation='study'
    return request_id,operation


def _error(request_id, operation, code, message, current_revision=None):
    error={'code':code,'message':message[:500],
           'retryable':code in ('MODEL_TIMEOUT','MODEL_BUSY','MODEL_UPSTREAM','MODEL_OUTPUT_INVALID','STORAGE_FAILED')}
    if current_revision is not None:error['current_revision']=current_revision
    result={'schema_version':'1.0','request_id':request_id,'operation':operation,'status':'error',
            'verification':{'level':'unavailable','label':'本次操作未完成'},'effects':[],'error':error}
    return contract.response(result),_STATUS[code]


def handle(payload):
    request_id,operation=_identity(payload)
    try:contract.request(payload)
    except contract.ContractError as error:
        return _error(request_id,operation,'INVALID_INPUT',str(error))
    try:
        result=invoke(payload['subject']['profile_id'],operation,payload['input'],request_id)
        response={'schema_version':'1.0','request_id':request_id,'operation':operation,**result}
        return contract.response(response),200
    except (DomainError,ConfirmationError) as error:
        return _error(request_id,operation,error.code,str(error),getattr(error,'current_revision',None))
    except ai.ModelError as error:
        code={'MODEL_AUTH_ERROR':'MODEL_AUTH','MODEL_UPSTREAM_ERROR':'MODEL_UPSTREAM',
              'MODEL_QUOTA_ERROR':'MODEL_BUSY','MODEL_OUTPUT_TRUNCATED':'MODEL_OUTPUT_INVALID',
              'TEACHING_OUTPUT_INVALID':'MODEL_OUTPUT_INVALID','TEACHING_MATH_FORMAT_INVALID':'MODEL_OUTPUT_INVALID'}.get(error.code,error.code)
        if code not in _STATUS:code='MODEL_UPSTREAM'
        return _error(request_id,operation,code,str(error))
    except OSError:
        return _error(request_id,operation,'STORAGE_FAILED','学习记录暂时无法保存或读取，请稍后重试。')
    except contract.ContractError:
        return _error(request_id,operation,'MODEL_OUTPUT_INVALID','学习结果没有通过结构检查，请稍后重试。')
    except (ValueError,TypeError):
        return _error(request_id,operation,'INVALID_INPUT','请求内容暂时无法处理，请核对字段后再试。')
