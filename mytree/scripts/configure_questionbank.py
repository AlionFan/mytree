#!/usr/bin/env python3
"""Enter provider credentials locally; nothing is sent or printed."""
import getpass
import json
import os
from pathlib import Path


def main():
    print('有道控制台：https://ai.youdao.com/console/ → 创建精品题库 API 应用。')
    print('仅本机保存；不会调用题库或购买套餐。两项输入均隐藏。')
    key=getpass.getpass('应用 ID（APP key）：').strip()
    secret=getpass.getpass('应用密钥：').strip()
    if not key or not secret or any(c.isspace() for c in key+secret) or max(len(key),len(secret))>256:
        raise SystemExit('格式不正确，未保存。')
    path=Path(__file__).resolve().parents[1]/'data/deployment/questionbank.json'
    path.parent.mkdir(parents=True,exist_ok=True);os.chmod(path.parent,0o700)
    temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump({'app_key':key,'app_secret':secret,'daily_limit':20},stream)
    os.chmod(temporary,0o600);os.replace(temporary,path)
    print('已私有保存。默认全站每天最多20次实际请求；失败也计次。部署后需以自编题做真实联通验证。')


if __name__=='__main__':main()
