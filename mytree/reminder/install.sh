#!/bin/sh
# Generates a plist only. The printed system-install commands require user action.
set -eu
reminder_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$reminder_dir/prepare_launch_agent.py" "$@"
