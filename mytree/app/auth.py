"""Email OTP accounts. Codes and sessions are never returned or logged."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formataddr
from http.cookies import SimpleCookie, CookieError
from .email_template import verification_email

COOKIE = 'mytree_session'
CODE_TTL = 600
SESSION_TTL = 7 * 86400


class AuthError(Exception):
    def __init__(self, message, code='AUTH_INVALID', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def enabled():
    return os.environ.get('MYTREE_AUTH_MODE') == 'email'


def _path():
    return Path(os.environ.get('MYTREE_AUTH_DB', str(Path(__file__).resolve().parents[1] / 'data' / 'auth.sqlite3')))


def _secret():
    value = os.environ.get('MYTREE_AUTH_SECRET', '')
    if not value:
        raise AuthError('账号服务尚未配置，请联系管理员。', 'AUTH_UNAVAILABLE', 503)
    return value.encode()


def _digest(value):
    return hmac.new(_secret(), value.encode(), hashlib.sha256).hexdigest()


@contextmanager
def _db():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, profile_id TEXT UNIQUE NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS codes(email TEXT PRIMARY KEY, digest TEXT NOT NULL, nonce TEXT NOT NULL, expires REAL NOT NULL, issued REAL NOT NULL, attempts INTEGER NOT NULL, sent INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY, email TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_sessions(digest TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rates(bucket TEXT NOT NULL, at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS rates_bucket_at ON rates(bucket, at);
        ''')
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except BaseException:
        if conn.in_transaction: conn.rollback()
        raise
    finally:
        conn.close()


def email_address(value):
    if not isinstance(value, str):
        raise AuthError('请输入有效的邮箱地址。')
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value):
        raise AuthError('请输入有效的邮箱地址。')
    return value


def smtp_settings():
    settings = {}
    file = Path(os.environ.get('MYTREE_SMTP_CONFIG', str(Path(__file__).resolve().parents[1] / 'data' / 'deployment' / 'smtp.json')))
    try:
        settings = json.loads(file.read_text())
    except FileNotFoundError:
        pass
    for key in ('HOST', 'PORT', 'USER', 'PASSWORD', 'FROM'):
        if 'MYTREE_SMTP_' + key in os.environ:
            settings[key.lower()] = os.environ['MYTREE_SMTP_' + key]
    return settings


def mail_ready():
    config = smtp_settings()
    return all(config.get(key) for key in ('host', 'user', 'password', 'from'))


def send_code(email, code):
    config = smtp_settings()
    if not mail_ready():
        raise AuthError('验证码邮件服务尚未开通，请稍后再试。', 'MAIL_UNAVAILABLE', 503)
    message = EmailMessage()
    message['From'] = formataddr(('小树同学', config['from']))
    message['To'] = email
    message['Subject'] = '小树同学 · 登录验证码'
    plain_text, html = verification_email(code, os.environ.get('MYTREE_PUBLIC_ORIGIN') or 'https://mytree.joybeat.cn')
    message.set_content(plain_text)
    message.add_alternative(html, subtype='html')
    message.get_payload()[-1].add_related(
        (Path(__file__).parent / 'assets' / 'crystal-hero-email.jpg').read_bytes(),
        maintype='image', subtype='jpeg', cid='<crystal-hero>', disposition='inline')
    try:
        with smtplib.SMTP_SSL(config['host'], int(config.get('port', 465)), timeout=15, context=ssl.create_default_context()) as client:
            client.login(config['user'], config['password'])
            refused = client.send_message(message)
            if refused:
                raise smtplib.SMTPException('recipient refused')
    except (OSError, smtplib.SMTPException, ValueError):
        raise AuthError('验证码邮件发送失败，请稍后重试。', 'MAIL_SEND_FAILED', 503) from None


def _limit(conn, bucket, now, window, maximum):
    count = conn.execute('SELECT COUNT(*) FROM rates WHERE bucket=? AND at>?', (bucket, now-window)).fetchone()[0]
    return count < maximum


def request_code(value, ip):
    email = email_address(value)
    _secret()
    if not mail_ready():
        raise AuthError('验证码邮件服务尚未开通，请稍后再试。', 'MAIL_UNAVAILABLE', 503)
    now = time.time()
    code = f'{secrets.randbelow(1000000):06d}'
    nonce = secrets.token_hex(16)
    with _db() as conn:
        conn.execute('DELETE FROM rates WHERE at<?', (now-86400,))
        conn.execute('DELETE FROM sessions WHERE expires<?', (now,))
        conn.execute('DELETE FROM codes WHERE issued<?', (now-86400,))
        old = conn.execute('SELECT issued FROM codes WHERE email=?', (email,)).fetchone()
        if old and old['issued'] > now-60:
            raise AuthError('请等待 60 秒后再获取验证码。', 'AUTH_RATE_LIMIT', 429)
        limits = [(_digest('email:'+email),86400,10), (_digest('send:'+ip),3600,20), ('all-send',3600,100)]
        if not all(_limit(conn,b,now,w,m) for b,w,m in limits):
            raise AuthError('验证码请求较多，请稍后再试。', 'AUTH_RATE_LIMIT', 429)
        for bucket, _, _ in limits:
            conn.execute('INSERT INTO rates VALUES (?,?)', (bucket, now))
        conn.execute('INSERT OR REPLACE INTO codes VALUES (?,?,?,?,?,0,0)', (email,_digest(email+':'+nonce+':'+code),nonce,now+CODE_TTL,now))
    try:
        send_code(email, code)
    except Exception:
        with _db() as conn:
            conn.execute('DELETE FROM codes WHERE email=? AND nonce=?', (email,nonce))
        raise
    with _db() as conn:
        conn.execute('UPDATE codes SET sent=1 WHERE email=? AND nonce=?', (email,nonce))
    return {'ok':True, 'message':'验证码已发送，请查看邮箱（也可检查垃圾邮件）。', 'retry_after':60, 'expires_in':CODE_TTL}


def verify_code(value, code, ip):
    email = email_address(value)
    if not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code):
        raise AuthError('请输入邮件中的 6 位验证码。')
    now = time.time()
    result = None
    error = None
    with _db() as conn:
        conn.execute('DELETE FROM rates WHERE at<?',(now-86400,))
        bucket = _digest('verify:'+ip)
        if not _limit(conn,bucket,now,600,60):
            raise AuthError('验证次数较多，请稍后再试。','AUTH_RATE_LIMIT',429)
        conn.execute('INSERT INTO rates VALUES (?,?)',(bucket,now))
        row = conn.execute('SELECT * FROM codes WHERE email=?',(email,)).fetchone()
        if not row or not row['sent'] or row['expires']<=now or row['attempts']>=5:
            error = AuthError('验证码无效或已过期，请重新获取。')
        elif not hmac.compare_digest(row['digest'],_digest(email+':'+row['nonce']+':'+code)):
            conn.execute('UPDATE codes SET attempts=attempts+1 WHERE email=?',(email,))
            error = AuthError('验证码不正确，请检查后重试。')
        else:
            conn.execute('DELETE FROM codes WHERE email=?',(email,))
            user = conn.execute('SELECT profile_id FROM users WHERE email=?',(email,)).fetchone()
            created = user is None
            profile_id = user['profile_id'] if user else 'u_'+secrets.token_hex(16)
            if created:
                conn.execute('INSERT INTO users VALUES (?,?,?)',(email,profile_id,now))
            token = secrets.token_urlsafe(32)
            conn.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,now+SESSION_TTL))
            result = {'email':email,'profile_id':profile_id,'created':created}, token
    # Raise after committing the attempt counters, including failed verification.
    if error: raise error
    return result


def session(cookie):
    token = cookie_token(cookie)
    if not token: return None
    with _db() as conn:
        row = conn.execute('SELECT users.email,users.profile_id FROM sessions JOIN users ON users.email=sessions.email WHERE digest=? AND expires>?', (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None


def cookie_token(header, name=COOKIE):
    if not header or len(header)>8192: return None
    try:
        jar=SimpleCookie();jar.load(header)
        value=jar[name].value if name in jar else ''
        return value if re.fullmatch(r'[A-Za-z0-9_-]{43}',value) else None
    except CookieError:
        return None


def logout(cookie):
    token = cookie_token(cookie)
    if token:
        with _db() as conn:
            conn.execute('DELETE FROM sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),))


def cookie_header(token='', clear=False):
    secure = '; Secure' if os.environ.get('MYTREE_COOKIE_SECURE','1')=='1' else ''
    return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else SESSION_TTL}{secure}'

# Administrator credentials and cookies are independent from email accounts.
ADMIN_COOKIE = 'mytree_admin'
ADMIN_TTL = 8 * 3600


def admin_settings():
    return {'username':os.environ.get('MYTREE_ADMIN_USER',''), 'salt':os.environ.get('MYTREE_ADMIN_SALT',''), 'hash':os.environ.get('MYTREE_ADMIN_HASH','')}


def admin_ready():
    config=admin_settings()
    return bool(config['username'] and re.fullmatch('[0-9a-f]{32}',config['salt']) and re.fullmatch('[0-9a-f]{128}',config['hash']))


def admin_login(username,password,ip):
    if not isinstance(username,str) or not isinstance(password,str) or len(username)>80 or len(password)>128:
        raise AuthError('管理员账号或密码不正确。','ADMIN_INVALID',401)
    now=time.time()
    with _db() as conn:
        conn.execute('DELETE FROM rates WHERE at<?',(now-86400,))
        limits=[(_digest('admin-login:'+ip),900,10),('admin-login-all',900,100)]
        if not all(_limit(conn,b,now,w,m) for b,w,m in limits):
            raise AuthError('登录尝试较多，请 15 分钟后重试。','AUTH_RATE_LIMIT',429)
        for bucket,_,_ in limits:conn.execute('INSERT INTO rates VALUES (?,?)',(bucket,now))
    config=admin_settings()
    valid=admin_ready()
    # Still perform a slow hash for wrong/missing usernames to avoid timing leaks.
    salt=bytes.fromhex(config['salt']) if valid else b'0'*16
    digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
    if not valid or not hmac.compare_digest(username.encode(),config['username'].encode()) or not hmac.compare_digest(digest,config['hash']):
        with _db() as conn:conn.execute('INSERT INTO rates VALUES (?,?)',('admin-login-failed',now))
        raise AuthError('管理员账号或密码不正确。','ADMIN_INVALID',401)
    token=secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute('DELETE FROM admin_sessions WHERE expires<?',(now,))
        conn.execute('INSERT INTO admin_sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),now+ADMIN_TTL))
    return token


def admin_session(header):
    token=cookie_token(header,ADMIN_COOKIE)
    if not token:return False
    with _db() as conn:
        return conn.execute('SELECT 1 FROM admin_sessions WHERE digest=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone() is not None


def admin_logout(header):
    token=cookie_token(header,ADMIN_COOKIE)
    if token:
        with _db() as conn:conn.execute('DELETE FROM admin_sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),))


def admin_cookie(token='',clear=False):
    return cookie_header(token,clear).replace(COOKIE+'=',ADMIN_COOKIE+'=',1).replace('Max-Age='+str(SESSION_TTL),'Max-Age='+str(ADMIN_TTL))


def admin_overview():
    with _db() as conn:
        count=conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        failures=conn.execute('SELECT COALESCE(SUM(attempts),0) FROM codes WHERE issued>?',(time.time()-86400,)).fetchone()[0]
        admin_failures=conn.execute('SELECT COUNT(*) FROM rates WHERE bucket=? AND at>?',('admin-login-failed',time.time()-86400)).fetchone()[0]
    return {'service':{'http_ready':True,'account_storage_ready':True},'account_count':count,
            'email_ready':mail_ready(),'admin_configured':admin_ready(),
            'failures':{'active_code_wrong_attempts_24h':failures,'admin_login_failures_24h':admin_failures},
            'note':'验证码错误数仅统计当前保留验证码的尝试；发送服务就绪不代表每封邮件已投递到收件箱。'}
