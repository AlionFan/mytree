#!/bin/sh
# Prints removal commands; does not unload or remove anything.
set -eu
exec "${PYTHON:-python3}" - <<'PY'
import os
from pathlib import Path
import shlex
label='cn.joybeat.mytree.reminder'
path=Path.home()/'Library/LaunchAgents'/(label+'.plist')
print('尚未停止或移除。确认后由你执行：')
print('launchctl bootout gui/'+str(os.getuid())+'/'+label)
print('rm -i '+shlex.quote(str(path)))
print('学习档案不会被删除。')
PY
