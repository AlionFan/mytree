#!/usr/bin/env python3
"""C2 验收探测（Claude 自己跑，不依赖执行方的自测）。

三条口径，每条在**新的学生档案**上独立验证，互不污染：
  口径 1  到期 → 弹一次
  口径 2  再运行一次 → 不重复弹
  口径 3  孩子点「今天不看」(snooze) 后 → 不弹
另外检查：待办最多 3 项、message 不含催促恐吓词、弹失败不得 ack。

通知默认走 MYTREE_NOTIFY_LOG：提醒程序不真弹，只往日志追加一行，验收不打扰用户。
--real：最后单独验一次真的系统通知。**会真的在屏幕上弹一条，必须由用户在场并同意后才加此参数。**
        探测程序自己不会替用户决定要不要弹。

前置：由调用者准备三个学生档案，各有一条已到期的复习任务（待办必须非空）：
  --student-fire    用于口径 1、2
  --student-snooze  用于口径 3
  --student-fail    用于“弹失败不得 ack”（可选）
本脚本不修改任何用户系统设置，不安装 launchd，不写 ~/Library。
用法：
  python3 tools/c2_probe.py --base http://127.0.0.1:8000 --reminder <mytree_reminder.py> \
      --student-fire A --student-snooze B [--student-fail C] [--real --student-real D]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

RESULTS = []
THREAT = ('再不', '来不及', '落后', '别人都', '必须马上', '赶紧', '否则')


def check(label, ok, extra=''):
    RESULTS.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ') + label + (' | ' + str(extra) if extra else ''))


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'_error': type(e).__name__}


def today(base, student):
    return call(base, 'GET', '/api/review/today?student=' + student)


def run_reminder(path, base, student, log=None, extra_env=None):
    env = dict(os.environ, MYTREE_BASE=base, MYTREE_STUDENT=student)
    env.pop('MYTREE_NOTIFY_LOG', None)
    if log:
        env['MYTREE_NOTIFY_LOG'] = log
    env.update(extra_env or {})
    p = subprocess.run([sys.executable, path], env=env, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout.strip()[:200], p.stderr.strip()[:200]


def lines(log):
    return len(open(log, encoding='utf-8').read().splitlines()) if os.path.exists(log) else 0


def precondition(base, student, label):
    code, t = today(base, student)
    ok = code == 200 and t.get('reminder_allowed') is True and bool(t.get('items'))
    check(f'前置[{label}]：该档案有到期待办且允许提醒', ok,
          f'HTTP {code} reminder_allowed={t.get("reminder_allowed")} 项数={len(t.get("items") or [])}')
    return t if ok else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--reminder', required=True)
    ap.add_argument('--student-fire', required=True)
    ap.add_argument('--student-snooze', required=True)
    ap.add_argument('--student-fail')
    ap.add_argument('--real', action='store_true', help='真弹一条系统通知；需用户在场同意')
    ap.add_argument('--student-real')
    a = ap.parse_args()
    tmp = tempfile.mkdtemp()

    # ---- 口径 1 + 2
    t = precondition(a.base, a.student_fire, '口径1/2')
    if t:
        check('待办最多 3 项', len(t['items']) <= 3, len(t['items']))
        check('返回含 reminder_key', bool(t.get('reminder_key')))
        msg = t.get('message') or ''
        check('message 非空', bool(msg), msg[:60])
        check('message 不含催促恐吓词', not any(w in msg for w in THREAT), [w for w in THREAT if w in msg])
        log = os.path.join(tmp, 'fire.log')
        rc, _, err = run_reminder(a.reminder, a.base, a.student_fire, log)
        check('口径1 第一次运行：退出码 0', rc == 0, err)
        check('口径1 第一次运行：弹出 1 条', lines(log) == 1, f'日志 {lines(log)} 行')
        code, t2 = today(a.base, a.student_fire)
        check('口径1 弹后服务端 reminder_allowed=false', t2.get('reminder_allowed') is False)
        rc, _, err = run_reminder(a.reminder, a.base, a.student_fire, log)
        check('口径2 再运行：退出码 0', rc == 0, err)
        check('口径2 再运行：不重复弹', lines(log) == 1, f'日志 {lines(log)} 行')

    # ---- 口径 3：今天不看
    t = precondition(a.base, a.student_snooze, '口径3')
    if t:
        key = t['reminder_key']
        code, body = call(a.base, 'POST', '/api/review/snooze', {'student': a.student_snooze, 'reminder_key': key})
        check('口径3 POST /api/review/snooze 成功', code == 200 and body.get('ok') is True, f'{code} {str(body)[:80]}')
        code, body2 = call(a.base, 'POST', '/api/review/snooze', {'student': a.student_snooze, 'reminder_key': key})
        check('口径3 同一 reminder_key 重复 snooze 幂等', code == 200 and body2.get('ok') is True, f'{code}')
        code, t2 = today(a.base, a.student_snooze)
        check('口径3 snooze 后服务端 reminder_allowed=false', t2.get('reminder_allowed') is False)
        log = os.path.join(tmp, 'snooze.log')
        rc, _, err = run_reminder(a.reminder, a.base, a.student_snooze, log)
        check('口径3 snooze 后运行：退出码 0', rc == 0, err)
        check('口径3 snooze 后运行：不弹', lines(log) == 0, f'日志 {lines(log)} 行')
        code, body = call(a.base, 'POST', '/api/review/snooze', {'student': a.student_snooze})
        check('snooze 缺 reminder_key 被拒', code in (400, 422), code)

    # ---- 弹失败不得 ack
    if a.student_fail:
        t = precondition(a.base, a.student_fail, '弹失败')
        if t:
            # 让通知日志指向一个不可写位置，模拟“弹失败”
            bad = os.path.join(tmp, 'no_such_dir', 'x.log')
            rc, _, err = run_reminder(a.reminder, a.base, a.student_fail, bad)
            code, t2 = today(a.base, a.student_fail)
            check('弹失败后：服务端仍 reminder_allowed=true（没有误 ack）', t2.get('reminder_allowed') is True,
                  f'rc={rc}')
            check('弹失败后：退出码仍为 0（不报错风暴）', rc == 0, err)

    # ---- 网络不通：静默失败
    log = os.path.join(tmp, 'down.log')
    rc, out, err = run_reminder(a.reminder, 'http://127.0.0.1:9', a.student_fire, log)
    check('服务不可达：退出码 0、不弹、不崩', rc == 0 and lines(log) == 0, f'rc={rc} log={lines(log)}')

    # ---- 真弹（需用户同意）
    if a.real:
        if not a.student_real:
            check('--real 需要 --student-real', False)
        elif precondition(a.base, a.student_real, '真弹'):
            print('\n>>> 即将真的弹出 1 条系统通知，请看屏幕。')
            rc, _, err = run_reminder(a.reminder, a.base, a.student_real, None)
            check('真弹：退出码 0', rc == 0, err)
            code, t2 = today(a.base, a.student_real)
            check('真弹后服务端 reminder_allowed=false（已 ack）', t2.get('reminder_allowed') is False)
            print('请人工确认屏幕上是否出现了通知；这一条脚本无法自动判断。')

    print('\n通过', sum(RESULTS), '/', len(RESULTS))
    return 0 if all(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
