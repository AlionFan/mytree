#!/usr/bin/env python3
"""Exercise the local learning loop over real HTTP with an isolated fake model.

Run with mytree/.venv/bin/python tools/e2e_loop_check.py --require-complete.
No production profile, external model, system notification or login item is used.
Missing features are reported as unimplemented, never as passing checks.
"""
import argparse
import base64
import copy
from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'mytree'), str(ROOT / 'mytree/tests')]
TZ = ZoneInfo('Asia/Shanghai')


class Unimplemented(Exception):
    pass


class FakeModel(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.calls += 1
        is_image = any(isinstance(m.get('content'), list) and any(
            isinstance(c, dict) and c.get('type') == 'image_url' for c in m['content'])
            for m in body.get('messages', []))
        result = self.server.ocr if is_image else {
            'hints': ['先看两项分别是什么。', '比较平方差与完全平方的结构。',
                      '平方差可分为两个因式：(x-3)(x+3)。'],
            'card': {'title': '平方差公式', 'body': '两个平方的差可以分解。', 'tip': '注意中间符号。'},
            'answer_latex': '(x-3)(x+3)', 'assessment': '请核对公式结构。',
            'knowledge_ids': ['F2'], 'reply': '先辨认两个平方。', 'equations': [],
        }
        data = json.dumps({'choices': [{'message': {'content': json.dumps(result, ensure_ascii=False)},
                                       'finish_reason': 'stop'}],
                           'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str) and value.startswith('data:image/'):
        return '<synthetic-image omitted from trace>'
    return value


class LoopCheck:
    STAGES = ['old_profile_compatibility', 'atomic_storage_failure', 'photo_confirmation',
              'wrong_card_and_replay', 'controlled_hint_access', 'review_tasks', 'reminder_state', 'quiz_verification',
              'knowledge_unlock', 'review_completion', 'tree_persistence_and_undo', 'reference_growth']

    def __init__(self, output):
        self.output = output
        self.trace = []
        self.results = []
        self.counter = 0
        self.student = 'e2e_loop_local'
        self.schema = json.loads((ROOT / 'docs/architecture/agent-contract.schema.json').read_text())

    def http(self, method, route, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + route, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.status
            payload = json.loads(response.read())
        self.trace.append({'method': method, 'path': route, 'request': scrub(body),
                           'http_status': status, 'response': payload})
        return status, payload

    def envelope(self, operation, values, request_id=None):
        self.counter += 1
        return {'schema_version': '1.0', 'operation': operation,
                'request_id': request_id or f'loop-{operation.replace(".", "-")}-{self.counter}',
                'client': {'type': 'web', 'name': 'isolated-e2e'},
                'subject': {'profile_id': self.student}, 'input': values,
                'options': {'language': 'zh-CN', 'modalities': ['text', 'svg']}}

    def agent(self, operation, values, request_id=None, expect_error=False):
        from app import contract
        request = self.envelope(operation, values, request_id)
        contract.request(request)
        status, response = self.http('POST', '/api/agent', request)
        error = response.get('error')
        if (status == 404 and not expect_error) or (isinstance(error, dict) and error.get('code') == 'UNSUPPORTED'):
            raise Unimplemented(operation + ' 的统一入口尚未实现')
        assert response.get('operation') == operation, (operation, status, scrub(response))
        contract.response(response)
        if expect_error:
            assert response['status'] == 'error', response
        else:
            assert status == 200 and response['status'] != 'error', (status, response)
        return request, response

    def step(self, name, action):
        try:
            detail = action()
            self.results.append({'stage': name, 'status': 'passed', 'detail': detail or '实际检查通过'})
            return True
        except Unimplemented as error:
            self.results.append({'stage': name, 'status': 'unimplemented', 'detail': str(error)})
        except Exception as error:
            self.results.append({'stage': name, 'status': 'failed',
                                 'detail': type(error).__name__ + ': ' + str(error)[:1800]})
        return False

    def legacy(self):
        from app import store
        status, result = self.http('GET', '/api/profile?student=legacy_loop')
        assert status == 200 and result['history'] == 7
        assert result['causes']['F-MIX-FORMULA'] == 2
        assert any(k['id'] == 'F2' and k['lit'] for k in result['tree'])
        value = store.read('legacy_loop')
        for key, kind in store.COLLECTIONS.items():
            assert isinstance(value[key], kind), key
        return '旧计数与点亮保留；新集合补空；HTTP读取成功'

    def storage_failure(self):
        from app import profile, store
        before = Path(profile._PATH).read_bytes()
        with patch('app.profile._save', side_effect=OSError('test-only failure')):
            try:
                store.update('legacy_loop', lambda p: p['wrong_cards'].update({'must_not_commit': {}}))
            except store.StorageFailed:
                pass
            else:
                raise AssertionError('写失败没有抛StorageFailed')
            status, result = self.http('POST', '/api/availability', {
                'student': 'legacy_loop', 'availability': {'days': [2], 'time': '18:15'}})
            assert status == 503 and result['code'] == 'STORAGE_FAILED', (status, result)
        assert Path(profile._PATH).read_bytes() == before, '失败写入改变了旧文件'
        return '内部事务与真实HTTP均拒绝写失败；磁盘字节未改变'

    def photo(self):
        _, before = self.http('GET', '/api/profile?student=' + self.student)
        self.read_request, response = self.agent('recognize', {'image_data': self.image})
        self.reading = response['output']
        assert response['status'] == 'needs_confirmation' and response['effects'] == []
        # Formatting delimiters added by the display adapter are harmless;
        # retain the actual mistaken expression rather than algebraically
        # simplifying it (which could conceal a changed student answer).
        written = [step.replace(r'\(', '').replace(r'\)', '').strip() for step in self.reading['steps']]
        assert written == ['(x-3)^2'], '学生原始错误被改写'
        _, after = self.http('GET', '/api/profile?student=' + self.student)
        assert after['history'] == before['history'] == 0
        return '真实HTTP经过本地假模型转录；确认前无学习进度'

    def wrong_card(self):
        values = {'confirmed_reading_id': self.reading['reading_id'],
                  'problem': self.reading['problem'], 'problem_latex': self.reading.get('problem_latex', ''),
                  'steps': self.reading['steps']}
        self.study_request, response = self.agent('study', values, 'loop-confirmed-study')
        self.wrong = response['output']['wrong_card']
        self.diagnosis_id = response['output']['diagnosis_id']
        assert len(response['output']['analysis'].get('hints', [])) <= 2, '诊断预发了第3级提示'
        assert response['output']['analysis']['hint_levels_available'] == 3
        assert self.wrong['student_steps'] == self.reading['steps'], '错题卡必须保留确认时的原样步骤，分析排版不能覆盖来源'
        assert 'F2' in self.wrong['knowledge_ids']
        _, replay = self.agent('study', values, 'loop-confirmed-study')
        assert replay['output']['wrong_card']['id'] == self.wrong['id']
        assert replay['output']['diagnosis_id'] == response['output']['diagnosis_id']
        _, cards = self.agent('card.list', {'type': 'wrong'})
        assert len(cards['output']['items']) == 1
        _, edited = self.agent('card.edit', {'card_id': self.wrong['id'],
                              'expected_revision': self.wrong['revision'], 'learner_note': '我把两个公式混淆了。'})
        assert edited['output']['card']['learner_note'] == '我把两个公式混淆了。'
        _, refreshed = self.agent('card.list', {'type': 'wrong'})
        saved = next(c for c in refreshed['output']['items'] if c['id'] == self.wrong['id'])
        assert saved['revision'] == edited['output']['revision']
        _, stale = self.agent('card.edit', {'card_id': self.wrong['id'],
                              'expected_revision': self.wrong['revision'], 'learner_note': '旧标签页的覆盖'}, expect_error=True)
        assert stale['error']['code'] == 'CONFLICT'
        assert stale['error']['current_revision'] == saved['revision']
        return '确认建卡、同请求重放不重复、笔记保存'

    def hints(self):
        maximum = 0
        for level in (1, 2, 3, 1):
            status, result = self.http('POST', '/api/hint', {
                'student': self.student, 'diagnosis_id': self.diagnosis_id, 'level': level})
            if status == 404:
                raise Unimplemented('受控提示通道尚未实现')
            assert status == 200 and result['level'] == level and result['text'], (status, result)
            assert result['scope'] == 'diagnosis'
            maximum = max(maximum, level)
            assert result['max_hint_level_recorded'] == maximum
        return '提示按请求发放并记录，读回低级提示不会降低记录；原题学习后仍可做新检验'

    def make_due(self):
        from app import profile, store
        at = datetime.now(TZ)
        def change(p):
            p['availability'] = {'days': [at.isoweekday()], 'time': at.strftime('%H:%M')}
            assert p['reviews'], '错题没有创建复习'
            for review in p['reviews'].values():
                review['due'] = (at - timedelta(minutes=1)).isoformat(timespec='seconds')
        store.update(self.student, change)

    def reviews(self):
        self.make_due()
        status, result = self.http('GET', '/api/review/today?student=' + self.student)
        if status == 404:
            raise Unimplemented('review.today 提醒适配尚未实现')
        assert status == 200, result
        self.today = result.get('output', result)
        _, agent_result = self.agent('review.today', {})
        assert agent_result['output'] == self.today, '提醒终端与Agent入口返回的待办不一致'
        assert 1 <= len(self.today['items']) <= 3
        assert self.today['reminder_allowed'] is True
        for item in self.today['items']:
            assert item['reason'] and item['task']['prompt']
        self.review_id = next(item['id'] for item in self.today['items'] if item['knowledge_id'] == 'F2')
        return '只修改临时测试档案的到期/空闲时间；真实待办带具体任务和理由'

    def reminder(self):
        from app import store
        from app import contract
        status, result = self.http('POST', '/api/review/ack', {
            'student': self.student, 'reminder_key': self.today['reminder_key']})
        if status == 404:
            raise Unimplemented('提醒ack尚未实现')
        assert status == 200, result
        contract.definition('ReviewAckResponse', result)
        _, result = self.http('GET', '/api/review/today?student=' + self.student)
        assert result.get('output', result)['reminder_allowed'] is False
        status, duplicate = self.http('POST', '/api/review/ack', {'student': self.student,
                  'reminder_key': self.today['reminder_key']})
        assert status == 200 and duplicate.get('duplicate') is True, duplicate
        store.update(self.student, lambda p: p['reminders'].clear())
        with tempfile.TemporaryDirectory(prefix='mytree-notify-check-') as temp:
            log = Path(temp) / 'notifications.jsonl'
            env = {'PATH': os.defpath, 'MYTREE_BASE': self.base, 'MYTREE_STUDENT': self.student,
                   'MYTREE_NOTIFY_LOG': str(log)}
            command = [sys.executable, str(ROOT / 'mytree/reminder/mytree_reminder.py')]
            for _ in range(2):
                run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=12)
                assert run.returncode == 0 and not run.stderr, '提醒程序与真实HTTP联调失败'
            assert len(log.read_text().splitlines()) == 1, '真实复习服务重复提醒'
            store.update(self.student, lambda p: p['reminders'].clear())
            env['MYTREE_NOTIFY_LOG'] = temp  # Delivery failure, no acknowledgement.
            run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=12)
            assert run.returncode == 0
            _, after_failure = self.http('GET', '/api/review/today?student=' + self.student)
            assert after_failure['reminder_allowed'] is True, '提醒失败却被确认'
        # Isolated fixture reset: prove snooze against a fresh eligible day,
        # rather than rechecking a day already suppressed by acknowledgement.
        store.update(self.student, lambda p: p['reminders'].clear())
        _, fresh = self.http('GET', '/api/review/today?student=' + self.student)
        assert fresh['reminder_allowed'] is True
        status, result = self.http('POST', '/api/review/snooze', {
            'student': self.student, 'reminder_key': fresh['reminder_key']})
        assert status == 200, result
        contract.definition('ReviewSnoozeResponse', result)
        _, result = self.http('GET', '/api/review/today?student=' + self.student)
        assert result.get('output', result)['reminder_allowed'] is False
        fixture = store.read(self.student)
        for suffix in ('fire', 'snooze', 'fail'):
            store.update('c2_probe_' + suffix, lambda p: p.update({
                'reviews': copy.deepcopy(fixture['reviews']), 'availability': copy.deepcopy(fixture['availability'])}))
        probe = subprocess.run([sys.executable, str(ROOT / 'tools/c2_probe.py'), '--base', self.base,
                                '--reminder', str(ROOT / 'mytree/reminder/mytree_reminder.py'),
                                '--student-fire', 'c2_probe_fire', '--student-snooze', 'c2_probe_snooze',
                                '--student-fail', 'c2_probe_fail'], capture_output=True, text=True, timeout=45)
        (self.output / 'c2-probe.txt').write_text(probe.stdout + probe.stderr)
        assert probe.returncode == 0, 'Claude独立编写的C2脚本失败，见c2-probe.txt'
        return '真实客户端子进程+HTTP：成功后确认、两次只发一条、失败不确认、全新待提醒状态今天跳过；不证明系统通知实际显示'

    def private_answer(self, quiz_id, item_id):
        from app import store
        value = store.read(self.student)
        quiz = value['quizzes'][quiz_id]
        items = quiz.get('items', [])
        item = items.get(item_id) if isinstance(items, dict) else next(
            (i for i in items if i.get('id') == item_id), None)
        assert item is not None, '临时服务端检验题不存在'
        for key in ('answer_latex', 'a', 'answer', 'expected_answer'):
            if isinstance(item.get(key), str):
                return item[key]
        raise AssertionError('请按实际私有存储字段适配测试oracle；不得使用客户端下发答案')

    def quiz(self):
        _, response = self.agent('quiz.start', {'knowledge_id': 'F2',
                                  'source_wrong_card_ids': [self.wrong['id']], 'review_id': self.review_id})
        self.quiz_data = response['output']
        self.answer_evidence = []
        assert len(self.quiz_data['items']) == 3
        assert any(i['is_transfer'] for i in self.quiz_data['items'])
        first = self.quiz_data['items'][0]
        # Deliberately bypass client-side validation: the HTTP boundary itself
        # must reject self-reported grading and forged server exercise IDs.
        forged = self.envelope('quiz.answer', {'quiz_id': self.quiz_data['quiz_id'],
                               'exercise_id': first['id'], 'answer': 'anything', 'correct': True, 'score': 100})
        status, rejected = self.http('POST', '/api/agent', forged)
        assert status == 400 and rejected.get('error', {}).get('code') == 'INVALID_INPUT', rejected
        self.agent('quiz.answer', {'quiz_id': self.quiz_data['quiz_id'],
                   'exercise_id': 'forged-exercise', 'answer': 'anything'}, expect_error=True)
        _, premature = self.agent('card.unlock', {'quiz_id': self.quiz_data['quiz_id']})
        assert premature['output']['unlocked'] is False and premature['output']['reasons']
        for item in self.quiz_data['items']:
            assert not ({'a', 'answer', 'expected', 'answer_latex', 'hints'} & set(item)), '检验泄露答案'
            answer = self.private_answer(self.quiz_data['quiz_id'], item['id'])
            _, result = self.agent('quiz.answer', {'quiz_id': self.quiz_data['quiz_id'],
                                   'exercise_id': item['id'], 'answer': answer})
            assert result['output']['correct'] is True
            assert result['output']['max_hint_level'] == 0
            self.answer_evidence.append(result['output']['evidence_id'])
            _, repeated = self.agent('quiz.answer', {'quiz_id': self.quiz_data['quiz_id'],
                                      'exercise_id': item['id'], 'answer': answer})
            assert repeated['output']['duplicate'] is True
            assert repeated['output']['evidence_id'] == result['output']['evidence_id']
            assert repeated['output']['progress'] == result['output']['progress']
        return '三题由服务端保存/批改；仅测试oracle读取临时私有答案，客户端无答案'

    def unlock(self):
        _, response = self.agent('card.unlock', {'quiz_id': self.quiz_data['quiz_id']})
        result = response['output']
        assert result['unlocked'] and all(result['checks'][f'U{i}'] for i in range(1, 6))
        self.knowledge = result['card']
        assert self.wrong['id'] in self.knowledge['source_wrong_card_ids']
        _, again = self.agent('card.unlock', {'quiz_id': self.quiz_data['quiz_id']})
        assert again['output']['card']['id'] == self.knowledge['id']
        _, cards = self.agent('card.list', {'type': 'knowledge'})
        assert len(cards['output']['items']) == 1
        return 'U1～U5通过才解锁；重复请求只有一张卡'

    def review_completion(self):
        values = {'review_id': self.review_id, 'evidence_ids': self.answer_evidence, 'self_report': 'remembered'}
        _, result = self.agent('review.complete', values, 'loop-review-complete')
        assert result['output']['completed'] is True
        assert result['output']['knowledge_card_eligible'] is False, '复习完成不能绕过单独解锁'
        _, repeated = self.agent('review.complete', values, 'loop-review-complete')
        assert repeated['output']['profile_fact_ids'] == result['output']['profile_fact_ids']
        _, today = self.agent('review.today', {})
        assert not any(item['id'] == self.review_id for item in today['output']['items'])
        return '服务端verified正确作答完成到期复习并排下一次；重放不重复计入事实'

    def tree(self):
        _, result = self.agent('tree.get', {})
        initial = result['output']
        card = self.knowledge['id']
        _, moved = self.agent('tree.move', {'action': 'move', 'method': 'drag', 'card_id': card,
                               'parent_id': None, 'position': {'x': 120, 'y': 80},
                               'expected_revision': initial['revision']})
        first = moved['output']
        _, conflict = self.agent('tree.move', {'action': 'move', 'method': 'keyboard', 'card_id': card,
                                  'parent_id': None, 'position': {'x': 999, 'y': 999},
                                  'expected_revision': initial['revision']}, expect_error=True)
        assert conflict['error']['code'] == 'CONFLICT'
        _, result = self.agent('tree.get', {})
        placement = next(p for p in result['output']['placements'] if p['card_id'] == card)
        assert placement['position'] == {'x': 120, 'y': 80}
        _, keyboard = self.agent('tree.move', {'action': 'move', 'method': 'keyboard', 'card_id': card,
                                  'parent_id': None, 'position': {'x': 240, 'y': 120},
                                  'expected_revision': first['revision']})
        self.agent('tree.move', {'action': 'undo', 'method': 'menu',
                   'undo_token': keyboard['output']['undo']['token'],
                   'expected_revision': keyboard['output']['revision']})
        _, result = self.agent('tree.get', {})
        assert next(p for p in result['output']['placements'] if p['card_id'] == card)['position'] == {'x': 120, 'y': 80}
        return 'HTTP拖动/键盘移动、重新读取、撤销与过期版本拒绝；实际UI另验'

    def growth(self):
        _, result = self.agent('growth.get', {})
        output = result['output']
        assert sum(output['components'].values()) == output['total']
        assert output['components']['scale'] == 10
        assert all(v >= 0 for v in output['components'].values())
        _, again = self.agent('growth.get', {})
        assert again['output']['total'] == output['total']
        return '参考成长分合计正确、无负数、重复读取不增加'

    def run(self, serve=False):
        from app import ai, profile
        from test_all import _serve
        from PIL import Image, ImageDraw
        started = time.monotonic()
        self.output.mkdir(parents=True, exist_ok=True)
        image = Image.new('RGB', (640, 360), 'white')
        ImageDraw.Draw(image).text((30, 40), 'Factor: x^2 - 9\nStudent: (x-3)^2\nSYNTHETIC TEST IMAGE', fill='black', font_size=28)
        stream = io.BytesIO(); image.save(stream, format='PNG')
        (self.output / 'synthetic-question.png').write_bytes(stream.getvalue())
        self.image = 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()
        with tempfile.TemporaryDirectory(prefix='mytree-loop-') as temp, ExitStack() as stack:
            path = Path(temp) / 'profiles.json'
            path.write_text(json.dumps({'legacy_loop': {'history': 7, 'causes': {'F-MIX-FORMULA': 2},
                            'lit': ['F2'], 'reviews': {}, 'events': []}}))
            upstream = ThreadingHTTPServer(('127.0.0.1', 0), FakeModel)
            upstream.calls = 0
            upstream.ocr = {'problem': 'x^2-9', 'problem_latex': 'x^2-9', 'steps': ['(x-3)^2'],
                            'question_type': 'factor', 'topic_id': 'F2', 'diagram_description': '',
                            'supported': True, 'multiple_questions': False, 'warnings': [], 'uncertain_lines': []}
            threading.Thread(target=upstream.serve_forever, daemon=True).start()
            stack.callback(upstream.server_close); stack.callback(upstream.shutdown)
            cfg = ai.Settings(f'http://127.0.0.1:{upstream.server_address[1]}/v1',
                              'LOCAL_TEST_ONLY', 'gpt-6.1-sol', 'gpt-6.1-sol', 5, 'low')
            stack.enter_context(patch('app.ai.settings', return_value=cfg))
            stack.enter_context(patch('app.ai.USAGE_PATH', Path(temp) / 'usage.jsonl'))
            stack.enter_context(patch('app.profile._PATH', str(path)))
            httpd, self.base = _serve()
            stack.callback(httpd.server_close); stack.callback(httpd.shutdown)
            if serve:
                print(json.dumps({'mode': 'isolated_browser_acceptance', 'base': self.base,
                                  'profile': str(path), 'synthetic_image': str(self.output / 'synthetic-question.png'),
                                  'model': 'local fake upstream; zero paid calls'}, ensure_ascii=False), flush=True)
                try:
                    while True:
                        threading.Event().wait(1)
                except KeyboardInterrupt:
                    return None
            self.step(self.STAGES[0], self.legacy)
            self.step(self.STAGES[1], self.storage_failure)
            actions = [self.photo, self.wrong_card, self.hints, self.reviews, self.reminder,
                       self.quiz, self.unlock, self.review_completion, self.tree, self.growth]
            ready = True
            for name, action in zip(self.STAGES[2:], actions):
                if ready:
                    ready = self.step(name, action)
                else:
                    self.results.append({'stage': name, 'status': 'unimplemented', 'detail': '前置步骤未完成，未执行'})
            calls = upstream.calls
        report = {'checked_at': datetime.now(TZ).isoformat(timespec='seconds'),
                  'elapsed_seconds': round(time.monotonic() - started, 2),
                  'scope': '隔离临时档案、真实本机HTTP、本地假模型；不是OCR质量评测',
                  'real_photos_sent': False, 'paid_model_calls': 0, 'fake_upstream_calls': calls,
                  'native_notification_verified': False, 'actual_drag_ui_verified': False,
                  'schema_sha256': hashlib.sha256((ROOT / 'docs/architecture/agent-contract.schema.json').read_bytes()).hexdigest(),
                  'stages': self.results, 'http_trace': self.trace}
        (self.output / 'e2e-loop.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        for row in self.results:
            print(f"{row['status']:14} {row['stage']}: {row['detail']}")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/evidence/phase-b')
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--serve', action='store_true', help='保持隔离假上游服务，供真实浏览器验收；Ctrl-C清理')
    args = parser.parse_args()
    report = LoopCheck(args.output).run(serve=args.serve)
    if report is None:
        return
    failed = any(s['status'] == 'failed' for s in report['stages'])
    incomplete = any(s['status'] != 'passed' for s in report['stages'])
    raise SystemExit(1 if failed else 2 if args.require_complete and incomplete else 0)


if __name__ == '__main__':
    main()
