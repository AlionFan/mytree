"""Atomic transactions for the single-process local demonstration profile.

Existing profile functions use the same lock, load and save operations. New
collections are initialized lazily; no old facts or unrelated fields are erased.
"""
import copy
import json
import hashlib
import re
import threading
import uuid
from contextlib import contextmanager

from . import profile
from .schedule import now
from .errors import DomainError


COLLECTIONS = {
    'wrong_cards': dict,
    'knowledge_cards': dict,
    'quizzes': dict,
    'quiz_answers': dict,
    'hint_views': list,
    'tree': dict,
    'growth_events': list,
    'reminders': dict,
}
_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_requests_lock = threading.Lock()
_active_requests = {}


class StorageFailed(OSError):
    code = 'STORAGE_FAILED'

    def __init__(self):
        super().__init__('学习记录暂时无法保存或读取，请稍后重试。')


def _identifier(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(label + '格式不正确')
    return value


def _load():
    try:
        data = profile._load()
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        raise StorageFailed() from None
    if not isinstance(data, dict):
        raise StorageFailed()
    return data


def _student(data, student):
    if student in data and not isinstance(data[student], dict):
        raise StorageFailed()
    value = profile._student(data, student)
    if any(not isinstance(value[key], expected) for key, expected in COLLECTIONS.items()):
        # A malformed collection must not be silently reset, losing saved work.
        raise StorageFailed()
    return value


def read(student):
    _identifier(student, '档案编号')
    with profile._lock:
        return copy.deepcopy(_student(_load(), student))


def update(student, change):
    """Run `change(profile)` and commit once; exceptions leave disk unchanged."""
    _identifier(student, '档案编号')
    if not callable(change):
        raise TypeError('变更必须是可调用函数')
    with profile._lock:
        data = _load()
        value = _student(data, student)
        result = change(value)
        try:
            profile._save(data)
        except OSError:
            raise StorageFailed() from None
        return copy.deepcopy(result)


def _diagnosis(value, diagnosis_id):
    result = next((event for event in value['events']
                   if event.get('id') == diagnosis_id and event.get('type') in ('diagnosis', 'lesson')), None)
    if result is None:
        result = next((card for card in value['wrong_cards'].values() if card.get('diagnosis_id')==diagnosis_id),None)
    if result is None:raise ValueError('没有找到这道题，请重新打开题目。')
    return result


def record_hint_view(student, diagnosis_id, level):
    """Record an actual hint access; answers cannot self-report this history."""
    _identifier(diagnosis_id, '题目编号')
    if type(level) is not int or level not in (1, 2, 3):
        raise ValueError('提示级别需要是1、2或3')

    def change(value):
        _diagnosis(value, diagnosis_id)
        existing = next((item for item in value['hint_views']
                         if item['diagnosis_id'] == diagnosis_id and item['level'] == level and not item.get('quiz_id')), None)
        if existing is None:
            existing = {'id': uuid.uuid4().hex, 'diagnosis_id': diagnosis_id,
                        'level': level, 'at': now().isoformat(timespec='seconds')}
            value['hint_views'].append(existing)
        maximum = max(item['level'] for item in value['hint_views'] if item['diagnosis_id'] == diagnosis_id and not item.get('quiz_id'))
        return {'diagnosis_id': diagnosis_id, 'max_hint_level': maximum, 'view_id': existing['id']}

    return update(student, change)


def max_hint_level(student, diagnosis_id):
    _identifier(diagnosis_id, '题目编号')
    value = read(student)
    _diagnosis(value, diagnosis_id)
    return max((item['level'] for item in value['hint_views'] if item['diagnosis_id'] == diagnosis_id and not item.get('quiz_id')), default=0)


@contextmanager
def request_lock(key):
    # References include waiting threads so a busy lock can never be evicted.
    with _requests_lock:
        entry = _active_requests.setdefault(key, {'lock': threading.RLock(), 'users': 0})
        entry['users'] += 1
    try:
        with entry['lock']:
            yield
    finally:
        with _requests_lock:
            entry['users'] -= 1
            if not entry['users']:
                del _active_requests[key]


def command(student, operation, request_id, payload, prepare, commit, validate=None):
    """Prepare outside the disk lock, then atomically commit result + receipt.

    The receipt contains a fingerprint rather than raw request contents. In-flight
    requests for the same intent share a lock and do not repeat model calls.
    """
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
        raise ValueError('请求编号不能为空且不超过64字')
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    key = operation + ':' + request_id

    def cached(value):
        previous = value.get('command_receipts', {}).get(key)
        if previous is None:
            return None
        if previous['fingerprint'] != digest:
            raise DomainError('CONFLICT', '同一请求编号对应的内容已改变，请重新发起。', 409)
        result = copy.deepcopy(previous['result'])
        if 'duplicate' in result.get('output', {}):
            result['output']['duplicate'] = True
        for effect in result.get('effects', []):
            effect['idempotent_replay'] = True
        return result

    with request_lock((student, key)):
        previous = cached(read(student))
        if previous is not None:
            return previous
        prepared = prepare()

        def change(value):
            previous = cached(value)
            if previous is not None:
                return previous
            result = commit(value, prepared)
            if validate is not None:
                validate(result)
            from . import contract
            contract.response({'schema_version':'1.0','request_id':request_id,'operation':operation,**result})
            value.setdefault('command_receipts', {})[key] = {'fingerprint': digest, 'result': copy.deepcopy(result)}
            return result

        return update(student, change)
