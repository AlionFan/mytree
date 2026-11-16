"""Crystal island OTP email; deterministic text and a public, non-tracking image without MIME attachments."""
from html import escape
from urllib.parse import urlsplit


def verification_email(code, public_origin="https://mytree.joybeat.cn"):
    origin = urlsplit(public_origin)
    if origin.scheme != 'https' or not origin.netloc or origin.username or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ValueError('A trusted HTTPS public origin is required')
    base = public_origin.rstrip('/')
    text = (
        f'小树同学 · 邮箱验证\n\n你的验证码是：{code}\n\n'
        '10 分钟内有效，仅可使用一次。请返回小树同学，在验证页面输入这 6 位数字。\n'
        '首次验证后将创建账号，已有账号将直接登录。\n\n'
        '请勿向他人提供验证码。如果不是你本人操作，请忽略这封邮件。\n'
        '这是一封系统邮件，请勿直接回复。\n\n'
        '小树同学\n'
        f'{base}'
    )
    html = (_HTML.replace('__CODE__', escape(str(code)))
            .replace('__ASSET_URL__', escape(base + '/mail-hero.jpg', quote=True))
            .replace('__HOME_URL__', escape(base + '/welcome', quote=True))
            .replace('__SITE_URL__', escape(base, quote=True))
            .replace('__SITE_LABEL__', escape(origin.netloc)))
    return text, html


_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小树同学登录验证码</title></head><body style="margin:0;padding:24px 12px;background:#f7f8f4;color:#26382e;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',Arial,sans-serif"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:white;border:1px solid #e3e8dc;border-radius:16px"><tr><td style="padding:28px 28px 12px;font-size:20px;font-weight:700">小树同学</td></tr><tr><td style="padding:4px 28px 16px;font-size:16px;line-height:26px">你的登录验证码</td></tr><tr><td style="padding:0 28px"><div style="padding:18px 12px;border:1px solid #dbe5d3;background:#f2f6ee;border-radius:12px;text-align:center;font-size:38px;font-weight:700;letter-spacing:8px;color:#1d3527">__CODE__</div></td></tr><tr><td style="padding:20px 28px;font-size:14px;line-height:24px">10 分钟内有效，仅可使用一次。请返回小树同学输入这6位数字。<br>不要把验证码告诉他人。如果不是你本人操作，请忽略这封邮件。</td></tr><tr><td style="padding:0 28px 22px;font-size:12px;line-height:22px;color:#667160">此邮件用于你主动申请的登录或注册。<br><a href="__SITE_URL__" style="color:#365b42">__SITE_LABEL__</a></td></tr><tr><td align="center" style="padding:0 28px 24px"><img src="__ASSET_URL__" alt="小树同学" width="280" style="display:block;max-width:100%;height:auto;border:0;border-radius:10px"></td></tr></table></td></tr></table></body></html>"""
