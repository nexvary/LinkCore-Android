#!/usr/bin/env bash
# Add Direct VPS to the existing FG Link Server 0.5 installation in place.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
SERVER_DIR="${FGRCK_INSTALL_DIR:-/opt/fg-link-server}"
LAB_DIR="${NEXVARY_MTTL_INSTALL_DIR:-/opt/nexvary-direct-mttl-lab}"
LAB_ENV="${NEXVARY_MTTL_ENV_FILE:-/etc/nexvary-direct-mttl-lab.env}"
MAC="${NEXVARY_MTTL_ALLOWED_MAC:-2CE032C7A520}"
[[ "$MAC" =~ ^[0-9A-Fa-f]{12}$ ]] || { echo 'Invalid MAC' >&2; exit 1; }
MAC="${MAC^^}"
[[ -f "$SERVER_DIR/.env" && -f "$SERVER_DIR/app/main.py" && -f "$SERVER_DIR/app/database.py" && -f "$LAB_DIR/server/direct_mttl_lab.py" ]] || { echo 'Existing 0.5 server/lab not found' >&2; exit 1; }
# Static inspection only: do not import or reconfigure the running database.
python3 - "$SERVER_DIR/app/main.py" <<'PY'
import ast, pathlib, sys
source = pathlib.Path(sys.argv[1]).read_text()
tree = ast.parse(source)
names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
if not {'_panel_guard', '_log', 'get_db'}.issubset(names):
    raise SystemExit('Not the expected deployed 0.5 API; stopped before changes')
PY
cd "$SERVER_DIR"
SERVICES=$(docker compose config --services)
grep -qx api <<< "$SERVICES" || { echo 'Expected api service' >&2; exit 1; }
OVERRIDE="$SERVER_DIR/docker-compose.override.yml"
if [[ -e "$OVERRIDE" ]] && ! grep -q '^# FG Link Direct VPS managed override$' "$OVERRIDE"; then
  echo 'Custom Compose override found; stopped without replacing it' >&2; exit 1
fi
GID=$(getent group fgrck-mttl-ipc | cut -d: -f3)
[[ "$GID" =~ ^[0-9]+$ ]] || { echo 'Existing Direct IPC group is missing' >&2; exit 1; }
STAGING=$(mktemp -d /tmp/fg-legacy-direct.XXXXXX)
trap 'rm -rf "$STAGING"' EXIT
git clone --depth 1 --single-branch --branch private/direct-mttl-lab https://github.com/nexvary/LinkCore-Android.git "$STAGING/repo"
SOURCE="$STAGING/repo/server"
BACKUP="$SERVER_DIR/direct-extension-backup-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -m 700 "$BACKUP"
cp -a "$SERVER_DIR/app" "$BACKUP/"
for item in .env Dockerfile requirements.txt docker-compose.yml docker-compose.override.yml; do
  [[ ! -e "$SERVER_DIR/$item" ]] || cp -a "$SERVER_DIR/$item" "$BACKUP/"
done
cp -a "$LAB_DIR/server/direct_mttl_lab.py" "$BACKUP/daemon.previous.py"
rollback(){
  trap - ERR
  echo 'Extension update failed; restoring previous application/config' >&2
  cp -a "$BACKUP/app/." "$SERVER_DIR/app/"
  cp -a "$BACKUP/.env" "$SERVER_DIR/.env"
  if [[ -f "$BACKUP/docker-compose.override.yml" ]]; then
    cp -a "$BACKUP/docker-compose.override.yml" "$OVERRIDE"
  else
    rm -f "$OVERRIDE"
  fi
  cd "$SERVER_DIR"
  docker compose up -d --build --no-deps api || true
  echo "Backup: $BACKUP" >&2
  exit 1
}
trap rollback ERR
# Keep the deployed Dockerfile, requirements, SQLite location and legacy routes.
for module in direct_mttl.py legacy_direct.py legacy_direct_ui.py; do
  install -m 0644 "$SOURCE/app/$module" "$SERVER_DIR/app/$module"
done
python3 - "$SERVER_DIR/app/main.py" "$SERVER_DIR/.env" "$LAB_ENV" "$MAC" <<'PY'
from pathlib import Path
import sys
main, cloud_env, lab_env, mac = sys.argv[1:]
path = Path(main)
source = path.read_text()
marker = '# FG_DIRECT_EXTENSION_V1'
if marker not in source:
    path.write_text(source.rstrip() + '\n\n' + marker + '\n'
                    'from .legacy_direct import install as _install_fg_direct\n'
                    '_install_fg_direct(app, engine, SessionLocal, _panel_guard, _log)\n')
for filename, updates in [
    (cloud_env, {'FGRCK_DIRECT_MTTL_MACS': mac}),
    (lab_env, {'NEXVARY_MTTL_ALLOWED_MAC': mac, 'NEXVARY_MTTL_ALLOW_CONTROL': '1'})]:
    env = Path(filename)
    content = env.read_text() if env.exists() else ''
    lines = [line for line in content.splitlines() if line.split('=', 1)[0] not in updates]
    env.write_text('\n'.join(lines + [f'{k}={v}' for k,v in updates.items()]) + '\n')
    env.chmod(0o600)
PY
cat > "$OVERRIDE" <<EOF
# FG Link Direct VPS managed override
services:
  api:
    environment:
      FGRCK_DIRECT_MTTL_MACS: \${FGRCK_DIRECT_MTTL_MACS:-}
      FGRCK_DIRECT_MTTL_SOCKET: /run/nexvary-direct-mttl/admin.sock
    group_add:
      - "$GID"
    volumes:
      - /run/nexvary-direct-mttl:/run/nexvary-direct-mttl:ro
EOF
python3 -m compileall -q "$SERVER_DIR/app/main.py" "$SERVER_DIR/app/direct_mttl.py" "$SERVER_DIR/app/legacy_direct.py" "$SERVER_DIR/app/legacy_direct_ui.py" "$SOURCE/direct_mttl_lab.py"
install -m 0755 "$SOURCE/direct_mttl_lab.py" "$LAB_DIR/server/direct_mttl_lab.py"
systemctl restart nexvary-direct-mttl-lab
docker compose config --quiet
docker compose up -d --build --no-deps api
# Verify health, registered direct session API and the unchanged authenticated panel.
docker compose exec -T api python - <<'PY'
import json, os, time, urllib.request
from app.direct_mttl import adapter
for attempt in range(20):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3) as r:
            health = json.load(r)
        assert health.get('status') == 'ok', health
        break
    except (OSError, AssertionError):
        if attempt == 19:
            raise
        time.sleep(1)
assert adapter.request('status')['ok']
headers = {'X-FG-Panel-Token': os.environ['FG_LINK_PANEL_TOKEN']}
request = urllib.request.Request('http://127.0.0.1:8080/panel/api/direct/devices', headers=headers)
with urllib.request.urlopen(request, timeout=5) as r:
    devices = json.load(r)['devices']
assert devices, 'Owner Direct MAC registration missing'
request = urllib.request.Request('http://127.0.0.1:8080/panel', headers=headers)
with urllib.request.urlopen(request, timeout=5) as r:
    assert b'id="fg-direct-vps"' in r.read()
print('Existing API + Direct IPC + protected panel: OK')
for device in devices:
    print('DIRECT VPS', device['mac'], 'online=', device['connected'], 'outlets=', len(device.get('outlets', [])))
PY
trap - ERR
printf 'Extension installed. Open /panel and physically test ON/OFF. Backup: %s\n' "$BACKUP"
