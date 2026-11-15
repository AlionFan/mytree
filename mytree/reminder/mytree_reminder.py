#!/usr/bin/env python3
"""One local reminder poll; notification delivery precedes server acknowledgement.

MYTREE_BASE, MYTREE_STUDENT configure the same local learning profile.
MYTREE_NOTIFY_LOG selects a test notifier and never displays a real notification.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

TITLE = '小树同学 · 今日复习'
TIMEOUT = 8
MAX_RESPONSE = 256_000


class ReminderError(Exception):
    pass


def settings(environ):
    base = environ.get('MYTREE_BASE', 'http://127.0.0.1:8000').rstrip('/')
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ReminderError('服务地址配置不正确')
    student = environ.get('MYTREE_STUDENT', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', student):
        raise ReminderError('请配置与网页相同的学习档案编号')
    return base, student


def call(base, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(base + path, data=body,
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise ReminderError('服务返回内容超出提醒范围')
            value = json.loads(data)
    except (OSError, ValueError, urllib.error.URLError):
        raise ReminderError('暂时连不上复习服务，本次检查结束') from None
    if not isinstance(value, dict):
        raise ReminderError('复习服务返回格式不正确')
    return value


def notify(title, message, environ):
    log = environ.get('MYTREE_NOTIFY_LOG')
    if 'MYTREE_NOTIFY_LOG' in environ:
        if not log:
            raise ReminderError('测试通知日志路径为空，本次不发送通知')
        # Exactly one JSON record per delivery, even when text contains newlines.
        with open(log, 'a', encoding='utf-8') as output:
            output.write(json.dumps({'title': title, 'message': message}, ensure_ascii=False) + '\n')
        return
    if sys.platform != 'darwin':
        raise ReminderError('系统通知只支持本机 macOS')
    # Pass all server text as argv. It is data, never AppleScript source.
    script = 'on run argv\n display notification (item 1 of argv) with title (item 2 of argv)\nend run'
    try:
        subprocess.run(['/usr/bin/osascript', '-e', script, '--', message, title],
                       check=True, timeout=TIMEOUT, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        raise ReminderError('系统通知未发送，本次不确认提醒') from None


@contextmanager
def single_poll(base, student):
    """Prevent overlapping local launchd/manual runs from showing two banners."""
    key = hashlib.sha256((base + '\n' + student).encode()).hexdigest()[:24]
    path = Path(tempfile.gettempdir()) / f'mytree-reminder-{os.getuid()}-{key}.lock'
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def poll(environ=None, delivery=None):
    environ = os.environ if environ is None else environ
    base, student = settings(environ)
    with single_poll(base, student) as acquired:
        if not acquired:
            return False
        today = call(base, '/api/review/today?' + urllib.parse.urlencode({'student': student}))
        if today.get('reminder_allowed') is not True:
            return False
        items, message, key = today.get('items'), today.get('message'), today.get('reminder_key')
        if (not isinstance(items, list) or not 1 <= len(items) <= 3 or
                not isinstance(message, str) or not message.strip() or len(message) > 800 or
                not isinstance(key, str) or not 1 <= len(key) <= 64):
            raise ReminderError('复习待办缺少有效的任务、文案或提醒编号')
        (delivery or (lambda title, text: notify(title, text, environ)))(TITLE, message)
        ack = call(base, '/api/review/ack', {'student': student, 'reminder_key': key})
        if ack.get('ok') is not True or ack.get('reminder_key') != key:
            raise ReminderError('提醒已发送，但服务端未确认；本次不循环重试')
        return True


def main(environ=None):
    try:
        poll(environ)
    except (ReminderError, OSError):
        # Do not print URLs, paths, upstream errors or learning content to logs.
        print('mytree-reminder: 本次检查未完成，请稍后检查服务连接或通知设置。', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
