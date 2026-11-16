"""OTP presentation and SMTP MIME integration, with no real mail sent."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from email import policy
from email.parser import BytesParser
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import auth
from app.email_template import verification_email


class EmailTemplateTests(unittest.TestCase):
    def test_plain_and_html_preserve_code_and_validity(self):
        plain, html = verification_email('012345')
        for body in (plain, html):
            self.assertIn('012345', body)
            self.assertIn('10 分钟内有效', body)
            self.assertIn('仅可使用一次', body)
            self.assertIn('如果不是你本人操作', body)
        self.assertNotIn('<table', plain)
        self.assertIn('src="https://mytree.joybeat.cn/mail-hero.jpg"', html)
        self.assertNotIn('cid:', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('http://', html)
        self.assertNotIn('email-code.html', html)
        self.assertNotIn('cid:mytree-product-card', html)
        self.assertNotIn('打开并复制', html)
        self.assertNotIn('onclick=', html)

    def test_sample_code_is_never_hardcoded(self):
        plain, html = verification_email('654321')
        for body in (plain, html):
            self.assertIn('654321', body)
            self.assertNotIn('012345', body)
        self.assertNotIn('__CODE__', html)
        self.assertNotIn('样例', html)

    def test_html_escapes_dynamic_content(self):
        plain, html = verification_email('<b>123456</b>')
        self.assertIn('<b>123456</b>', plain)
        self.assertNotIn('<b>123456</b>', html)
        self.assertIn('&lt;b&gt;123456&lt;/b&gt;', html)

    def test_only_trusted_https_origin_is_accepted(self):
        for origin in ('javascript:alert(1)', 'https://user@evil.test', 'http://example.test', 'https://example.test/?redirect=evil'):
            with self.assertRaises(ValueError):
                verification_email('012345', origin)
        _, html = verification_email('012345', 'https://example.test')
        self.assertIn('https://example.test/mail-hero.jpg', html)

    def test_smtp_sends_plain_and_html_alternatives(self):
        config = {'host':'smtp.example.test','port':465,'user':'test','password':'test-only','from':'sender@example.test'}
        with patch('app.auth.smtp_settings', return_value=config), patch('app.auth.smtplib.SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            auth.send_code('recipient@example.test', '012345')
            message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertLess(len(message.as_bytes(policy=policy.SMTP)), 16 * 1024)
        parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
        self.assertEqual(parsed.get_content_type(), 'multipart/alternative')
        self.assertEqual([p.get_content_type() for p in parsed.iter_parts()], ['text/plain','text/html'])
        self.assertFalse(list(parsed.iter_attachments()))
        self.assertFalse(any(p.get_content_maintype() == 'image' for p in parsed.walk()))
        self.assertIsNotNone(parsed['Date'])
        self.assertTrue(str(parsed['Message-ID']).endswith('@example.test>'))
        self.assertEqual(parsed['Auto-Submitted'], 'auto-generated')
        self.assertEqual(parsed['To'], 'recipient@example.test')
        self.assertEqual(str(parsed['Subject']), '小树同学 · 登录验证码')
        for kind in ('plain', 'html'):
            self.assertIn('012345', parsed.get_body(preferencelist=(kind,)).get_content())


if __name__ == '__main__':
    unittest.main()
