import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mytree_reminder', HERE / 'mytree_reminder.py')
reminder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reminder)


class Service(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.server.events.append('get')
        payload = self.server.today.copy()
        if self.server.acknowledged:
            payload['reminder_allowed'] = False
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.events.append('ack')
        self.server.acks.append(body)
        self.server.acknowledged = True
        raw = json.dumps({'ok': True, 'reminder_key': body['reminder_key']}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Service)
        self.server.events = []
        self.server.acks = []
        self.server.acknowledged = False
        self.server.today = {'reminder_allowed': True, 'reminder_key': 'today-local-1',
                             'message': '今天有1个小任务：回想平方差公式。', 'items': [{'id': 'F2'}]}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.env = {'MYTREE_BASE': f'http://127.0.0.1:{self.server.server_address[1]}',
                    'MYTREE_STUDENT': 'reminder_test',
                    'MYTREE_NOTIFY_LOG': str(Path(self.temp.name) / 'notifications.jsonl')}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def test_delivery_precedes_ack_and_next_poll_does_not_repeat(self):
        def delivered(title, message):
            self.assertEqual(title, reminder.TITLE)
            self.assertEqual(message, self.server.today['message'])
            self.server.events.append('notify')
        self.assertTrue(reminder.poll(self.env, delivered))
        self.assertFalse(reminder.poll(self.env, delivered))
        self.assertEqual(self.server.events, ['get', 'notify', 'ack', 'get'])
        self.assertEqual(self.server.acks, [{'student': 'reminder_test', 'reminder_key': 'today-local-1'}])

    def test_today_skipped_or_outside_window_never_delivers(self):
        self.server.today['reminder_allowed'] = False
        with patch.object(reminder, 'notify') as notify:
            self.assertFalse(reminder.poll(self.env))
            notify.assert_not_called()
        self.assertFalse(self.server.acks)

    def test_delivery_failure_does_not_ack(self):
        def failure(*_):
            raise OSError('local test only')
        with self.assertRaises(OSError):
            reminder.poll(self.env, failure)
        self.assertEqual(self.server.events, ['get'])
        self.assertFalse(self.server.acks)

    def test_test_notifier_writes_one_line_and_never_calls_osascript(self):
        self.server.today['message'] = '一个任务\n包含换行与"引号"。'
        with patch.object(reminder.subprocess, 'run') as command:
            self.assertEqual(reminder.main(self.env), 0)
            command.assert_not_called()
        lines = Path(self.env['MYTREE_NOTIFY_LOG']).read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])['message'], self.server.today['message'])

    def test_unwritable_notifier_does_not_ack(self):
        self.env['MYTREE_NOTIFY_LOG'] = self.temp.name  # Directory, not a file.
        self.assertEqual(reminder.main(self.env), 0)
        self.assertFalse(self.server.acks)

    def test_empty_log_setting_never_falls_back_to_real_notification(self):
        self.env['MYTREE_NOTIFY_LOG'] = ''
        with patch.object(reminder.subprocess, 'run') as command:
            self.assertEqual(reminder.main(self.env), 0)
            command.assert_not_called()
        self.assertFalse(self.server.acks)

    def test_empty_or_excess_tasks_or_missing_message_do_not_ack(self):
        for update in ({'items': []}, {'items': [1, 2, 3, 4]}, {'message': ''}, {'reminder_key': ''}):
            old = self.server.today.copy()
            self.server.today.update(update)
            self.assertEqual(reminder.main(self.env), 0)
            self.assertFalse(self.server.acks)
            self.server.today = old

    def test_network_failure_is_one_safe_line_and_zero_exit(self):
        with patch.object(reminder.urllib.request, 'urlopen', side_effect=OSError('DO_NOT_PRINT')) as request:
            with patch('sys.stderr') as err:
                self.assertEqual(reminder.main(self.env), 0)
            self.assertEqual(request.call_count, 1)
            self.assertNotIn('DO_NOT_PRINT', str(err.write.call_args_list))
        self.assertFalse(self.server.acks)

    def test_ack_failure_does_not_retry_in_a_loop(self):
        actual = reminder.call
        def failing_ack(base, path, payload=None):
            if payload is not None:
                raise reminder.ReminderError('fake ack failure')
            return actual(base, path, payload)
        with patch.object(reminder, 'call', side_effect=failing_ack) as calls:
            self.assertEqual(reminder.main(self.env), 0)
            self.assertEqual(calls.call_count, 2)
        self.assertEqual(len(Path(self.env['MYTREE_NOTIFY_LOG']).read_text().splitlines()), 1)

    def test_overlapping_local_poll_skips_second(self):
        with reminder.single_poll(self.env['MYTREE_BASE'], self.env['MYTREE_STUDENT']) as held:
            self.assertTrue(held)
            self.assertFalse(reminder.poll(self.env))
        self.assertFalse(self.server.events)

    def test_server_text_is_only_an_argument_never_applescript(self):
        message = '" & do shell script "false" & "'
        with patch.object(reminder.sys, 'platform', 'darwin'), patch.object(reminder.subprocess, 'run') as run:
            reminder.notify(reminder.TITLE, message, {})
        args = run.call_args.args[0]
        self.assertNotIn(message, args[2])
        self.assertEqual(args[-2:], [message, reminder.TITLE])
        self.assertTrue(run.call_args.kwargs['check'])
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_configuration_rejects_identity_paths_and_embedded_credentials(self):
        for env in ({'MYTREE_STUDENT': '../x'}, {'MYTREE_STUDENT': ''},
                    {'MYTREE_STUDENT': 'ok', 'MYTREE_BASE': 'http://user:password@127.0.0.1'},
                    {'MYTREE_STUDENT': 'ok', 'MYTREE_BASE': 'file:///tmp/anything'}):
            with self.assertRaises(reminder.ReminderError):
                reminder.settings(env)

    def test_installer_only_generates_reviewable_plist(self):
        output = Path(self.temp.name) / 'review output'
        result = subprocess.run([sys.executable, str(HERE / 'prepare_launch_agent.py'), '--student',
                                 'reminder_test', '--base', self.env['MYTREE_BASE'], '--output', str(output)],
                                capture_output=True, text=True, check=True)
        with (output / 'cn.joybeat.mytree.reminder.plist').open('rb') as file:
            plist = plistlib.load(file)
        self.assertEqual(plist['StartInterval'], 900)
        self.assertEqual(plist['EnvironmentVariables']['MYTREE_STUDENT'], 'reminder_test')
        self.assertIn('launchctl bootstrap', result.stdout)
        self.assertTrue(Path(plist['ProgramArguments'][1]).is_file())
        self.assertNotIn('MYTREE_NOTIFY_LOG', plist['EnvironmentVariables'])
        self.assertEqual(os.stat(output / 'cn.joybeat.mytree.reminder.plist').st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
