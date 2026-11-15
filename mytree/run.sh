#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '请先运行：uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt'
  exit 1
fi
exec .venv/bin/python -m app.server
