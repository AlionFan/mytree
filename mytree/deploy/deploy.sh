#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
deploy_host="${MYTREE_SSH_HOST:-joybeat}"
release_name="mytree-$(date -u +%Y%m%dT%H%M%SZ)"
work_dir="$(mktemp -d -t mytree-deploy)"
trap 'rm -rf "$work_dir"' EXIT
# Explicit allow-list: no local profiles, keys, exams, eval data, or test oracle.
tar --exclude='__pycache__' --exclude='*.pyc' -czf "$work_dir/source.tgz" mytree/app mytree/web mytree/requirements.txt mytree/deploy docs/architecture/agent-contract.schema.json
mytree/.venv/bin/python - <<'PY'
from pathlib import Path
import json,os,secrets
from mytree.app import ai,question_search
cfg=ai.settings()
if not cfg.key:raise SystemExit('模型key未配置，未部署。')
p=Path('mytree/data/deployment');p.mkdir(parents=True,exist_ok=True);os.chmod(p,0o700)
private=p/'auth-secret.json'
if private.exists():secret=json.loads(private.read_text())['secret']
else:
 secret=secrets.token_urlsafe(48)
 fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:json.dump({'secret':secret},f)
from mytree.app import auth
smtp=auth.smtp_settings()
bank_key,bank_secret,bank_limit=question_search.settings()
admin=json.loads((p/'admin.json').read_text()) if (p/'admin.json').exists() else {}
values={'MYTREE_YOUDAO_APP_KEY':bank_key,'MYTREE_YOUDAO_APP_SECRET':bank_secret,'MYTREE_QUESTIONBANK_DAILY_LIMIT':str(bank_limit),'MYTREE_QUESTIONBANK_DB':'/data/questionbank.sqlite3','MYTREE_API_BASE':cfg.base,'MYTREE_API_KEY':cfg.key,'MYTREE_VISION_MODEL':cfg.vision,'MYTREE_TUTOR_MODEL':cfg.tutor,'MYTREE_DIAGRAM_MODEL':cfg.diagram,
'MYTREE_MODEL_TIMEOUT':str(cfg.timeout),'MYTREE_REASONING_EFFORT':cfg.reasoning,'MYTREE_ASR_MODEL':cfg.asr,'MYTREE_TTS_MODEL':cfg.tts,'MYTREE_TTS_VOICE':cfg.voice,
**{'MYTREE_ADMIN_'+key.upper():str(admin.get(field,'')) for key,field in (('user','username'),('salt','salt'),('hash','hash'))},
'MYTREE_AUTH_MODE':'email','MYTREE_AUTH_SECRET':secret,'MYTREE_PUBLIC_ORIGIN':'https://mytree.joybeat.cn',
'MYTREE_AUTH_DB':'/data/auth.sqlite3','MYTREE_COOKIE_SECURE':'1','MYTREE_TRUST_PROXY':'1',
**{'MYTREE_SMTP_'+key.upper():str(smtp.get(key,'')) for key in ('host','port','user','password','from')}}
assert not any('\n' in value or '\r' in value for value in values.values())
fd=os.open(p/'runtime.env',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:f.write(''.join(key+'='+value+'\n' for key,value in values.items()))
PY
scp -q "$work_dir/source.tgz" "$deploy_host:/home/ubuntu/mytree-source.tgz"
scp -q mytree/data/deployment/runtime.env "$deploy_host:/home/ubuntu/mytree-runtime.env"
ssh "$deploy_host" bash -s -- "$release_name" <<'REMOTE'
set -euo pipefail
umask 077
release="/srv/data/mytree/releases/$1"
previous="$(sudo -n readlink -f /srv/data/mytree/current 2>/dev/null || true)"
sudo -n install -d -m 755 "$release"
sudo -n install -d -m 700 /srv/data/mytree/private
sudo -n install -d -m 700 -o 10001 -g 10001 /srv/data/mytree/data
sudo -n tar -xzf /home/ubuntu/mytree-source.tgz -C "$release"
sudo -n docker build -q --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple -t "mytree:$1" -f "$release/mytree/deploy/Dockerfile" "$release"
if sudo -n test -f /srv/data/mytree/private/runtime.env; then sudo -n cp -p /srv/data/mytree/private/runtime.env /srv/data/mytree/private/previous.env; fi
sudo -n install -m 600 /home/ubuntu/mytree-runtime.env /srv/data/mytree/private/runtime.env
rm -f /home/ubuntu/mytree-runtime.env /home/ubuntu/mytree-source.tgz
printf 'MYTREE_IMAGE=mytree:%s\n' "$1" | sudo -n tee "$release/mytree/deploy/.env" >/dev/null
rollback() {
 if [ -n "$previous" ] && sudo -n test -f "$previous/mytree/deploy/compose.yaml"; then
  if sudo -n test -f /srv/data/mytree/private/previous.env; then sudo -n cp -p /srv/data/mytree/private/previous.env /srv/data/mytree/private/runtime.env; fi
  sudo -n docker compose -p mytree -f "$previous/mytree/deploy/compose.yaml" --env-file "$previous/mytree/deploy/.env" up -d
 else
  sudo -n docker rm -f mytree >/dev/null 2>&1 || true
 fi
}
trap rollback ERR
sudo -n docker compose -p mytree -f "$release/mytree/deploy/compose.yaml" --env-file "$release/mytree/deploy/.env" up -d
verified=0
for attempt in $(seq 1 24); do
 health="$(sudo -n docker inspect mytree --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}')"
 code="$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' https://mytree.joybeat.cn/ || true)"
 private_code="$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' https://mytree.joybeat.cn/tree || true)"
 login_code="$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' https://mytree.joybeat.cn/login || true)"
 if [ "$health" = healthy ] && [ "$code" = 200 ] && [ "$private_code" = 303 ] && [ "$login_code" = 200 ]; then verified=1; break; fi
 sleep 3
done
if [ "$verified" != 1 ]; then printf 'Health or trusted HTTPS verification failed\n' >&2; false; fi
sudo -n ln -sfn "$release" /srv/data/mytree/current
trap - ERR
printf 'Published: https://mytree.joybeat.cn/\nRelease: %s\n' "$release"
sudo -n docker inspect mytree --format 'Container: {{.State.Status}} | Health: {{.State.Health.Status}}'
REMOTE

# The prior shared website password is no longer an active credential.
rm -f mytree/data/deployment/access.json
