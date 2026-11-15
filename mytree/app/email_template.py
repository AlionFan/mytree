"""Crystal island OTP email; deterministic text and one compact inline JPEG."""
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
        '小树同学 · 复习 Agent\n每次复习，点亮新世界。\n'
        f'了解小树同学：{base}/welcome'
    )
    html = (_HTML.replace('__CODE__', escape(str(code)))
            .replace('__HOME_URL__', escape(base + '/welcome', quote=True))
            .replace('__SITE_URL__', escape(base, quote=True))
            .replace('__SITE_LABEL__', escape(origin.netloc)))
    return text, html


_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>小树同学 · 邮箱验证</title></head>
<body style="margin:0;padding:0;background-color:#0a1025;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',Arial,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;mso-hide:all;">你的验证码是__CODE__，10分钟内有效。</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0a1025;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;background-color:#fcfbff;border:1px solid #2c2e50;border-radius:20px;overflow:hidden;">
<tr><td style="padding:0;"><a href="__HOME_URL__" style="display:block;"><img src="cid:crystal-hero" width="560" alt="小树同学 · 复习Agent。每次复习，点亮新世界。" style="display:block;width:100%;max-width:560px;height:auto;border:0;border-radius:19px 19px 0 0;"></a></td></tr>
<tr><td style="padding:28px 26px 26px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="font-size:11px;line-height:18px;font-weight:700;letter-spacing:2px;color:#7765aa;padding-bottom:8px;">邮箱验证</td></tr>
<tr><td style="font-size:25px;line-height:36px;font-weight:700;color:#22243d;padding-bottom:12px;">准备好，继续你的探索。</td></tr>
<tr><td style="font-size:14px;line-height:24px;color:#6e6e86;padding-bottom:20px;">请在小树同学输入下方验证码，完成登录或注册。</td></tr>
<tr><td align="center" style="background-color:#121a38;border:1px solid #4e4674;border-radius:14px;padding:20px 8px 18px;">
<div style="font-size:11px;line-height:18px;color:#c1b2ee;padding-bottom:9px;letter-spacing:2px;">你的验证码</div>
<div dir="ltr" style="font-family:Consolas,'SFMono-Regular','Liberation Mono',monospace;font-size:42px;line-height:54px;font-weight:700;letter-spacing:10px;color:#ffffff;white-space:nowrap;">__CODE__</div>
<div style="font-size:12px;line-height:20px;color:#bcb8d4;padding-top:8px;">10 分钟内有效 &nbsp;·&nbsp; 仅可使用一次</div>
</td></tr>
<tr><td style="padding-top:18px;font-size:12px;line-height:22px;color:#858397;">请勿向他人提供验证码。<br>如果不是你本人操作，请忽略这封邮件。</td></tr>
<tr><td style="padding-top:20px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="border-top:1px solid #e7e3ef;padding-top:16px;font-size:11px;line-height:20px;color:#9690a5;">小树同学 · 复习 Agent</td><td align="right" style="border-top:1px solid #e7e3ef;padding-top:16px;font-size:11px;line-height:20px;"><a href="__SITE_URL__" style="color:#7765aa;text-decoration:none;">__SITE_LABEL__</a></td></tr></table></td></tr>
</table>
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;"><tr><td align="center" style="padding:16px 12px 0;font-size:10px;line-height:18px;color:#81869f;">这是一封系统邮件，请勿直接回复。</td></tr></table>
</td></tr></table></body></html>"""
