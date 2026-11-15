#!/usr/bin/env python3
"""Run in a local terminal; the QQ SMTP authorization code stays private."""
from getpass import getpass
from pathlib import Path
import json
import os
import tempfile

root=Path(__file__).resolve().parents[1]
directory=root/'data'/'deployment'
directory.mkdir(parents=True,exist_ok=True)
os.chmod(directory,0o700)
print('小树同学 · QQ 邮箱发信配置')
print('发件邮箱：1317483655@qq.com；服务器：smtp.qq.com；SSL端口：465')
password=getpass('粘贴 QQ 邮箱 SMTP 授权码（输入不显示）：').strip()
if not password or any(c.isspace() for c in password):
    raise SystemExit('授权码不能为空或包含空白，未保存。')
fd,temporary=tempfile.mkstemp(dir=directory,prefix='.smtp-',text=True)
try:
    with os.fdopen(fd,'w') as file:
        json.dump({'host':'smtp.qq.com','port':465,'user':'1317483655@qq.com','from':'1317483655@qq.com','password':password},file)
    os.replace(temporary,directory/'smtp.json')
finally:
    if os.path.exists(temporary):os.unlink(temporary)
print('已保存到本机私有配置，文件权限 0600。授权码未显示、未发送到聊天。')
print('请回到 Codex 告知“已填写”，继续部署与实际验证码验证。')
