"""Optional single-household preview gate; not a multi-user account system."""
import base64
from collections import deque
import hashlib
import hmac
import os
import threading
import time
from urllib.parse import urlparse

_lock=threading.Lock()
_calls=deque()


def enabled():return os.environ.get('MYTREE_AUTH_MODE')=='email' or bool(os.environ.get('MYTREE_ACCESS_PASSWORD'))


def authorized(header):
    password=os.environ.get('MYTREE_ACCESS_PASSWORD','')
    if not password:return os.environ.get('MYTREE_REQUIRE_AUTH')!='1'
    if not isinstance(header,str) or len(header)>1024 or not header.startswith('Basic '):return False
    try:
        actual=base64.b64decode(header[6:],validate=True).decode('utf-8')
        expected=os.environ.get('MYTREE_ACCESS_USER','tree')+':'+password
        return hmac.compare_digest(hashlib.sha256(actual.encode()).digest(),hashlib.sha256(expected.encode()).digest())
    except (ValueError,UnicodeDecodeError):return False


def same_origin(origin,host):
    if not enabled() or not origin:return True
    try:
        parsed=urlparse(origin)
        return parsed.scheme in ('https','http') and parsed.netloc==host and not parsed.username and not parsed.password
    except ValueError:return False


def allow_model():
    if not enabled():return True
    instant=time.monotonic()
    with _lock:
        while _calls and instant-_calls[0]>=60:_calls.popleft()
        if len(_calls)>=60:return False
        _calls.append(instant);return True
