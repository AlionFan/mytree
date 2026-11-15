#!/usr/bin/env python3
"""Generate a reviewable plist in an output directory; never installs or loads it."""
import argparse
import os
from pathlib import Path
import plistlib
import re
import shlex
import sys
import urllib.parse

LABEL = 'cn.joybeat.mytree.reminder'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--student', required=True)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    url = urllib.parse.urlparse(args.base)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.student):
        parser.error('student格式不正确')
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error('服务地址格式不正确')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output.resolve() / (LABEL + '.plist')
    # Template is an ordinary plist, with replacements serialized by plistlib.
    with Path(__file__).with_name(LABEL + '.plist.template').open('rb') as source:
        value = plistlib.load(source)
    value['ProgramArguments'] = [str(args.python.resolve()), str(Path(__file__).with_name('mytree_reminder.py').resolve())]
    value['EnvironmentVariables'] = {'MYTREE_BASE': args.base.rstrip('/'), 'MYTREE_STUDENT': args.student}
    value['StandardErrorPath'] = str(args.output.resolve() / 'reminder-error.log')
    with target.open('wb') as output:
        plistlib.dump(value, output)
    target.chmod(0o600)
    destination = Path.home() / 'Library/LaunchAgents' / target.name
    print('已生成待审查配置：' + str(target))
    print('尚未安装或启动。确认后由你执行：')
    print('mkdir -p ' + shlex.quote(str(destination.parent)))
    print('cp ' + shlex.quote(str(target)) + ' ' + shlex.quote(str(destination)))
    print('chmod 600 ' + shlex.quote(str(destination)))
    print('launchctl bootstrap gui/' + str(os.getuid()) + ' ' + shlex.quote(str(destination)))


if __name__ == '__main__':
    main()
