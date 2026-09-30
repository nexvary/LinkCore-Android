#!/usr/bin/env bash
# Upgrade only the already-working 0.5 Direct extension; preserve its runtime/config.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
SERVER_DIR="${FGRCK_INSTALL_DIR:-/opt/fg-link-server}"
LAB_DIR="${NEXVARY_MTTL_INSTALL_DIR:-/opt/nexvary-direct-mttl-lab}"
DROPIN_DIR="${NEXVARY_MTTL_SYSTEMD_DROPIN_DIR:-/etc/systemd/system/nexvary-direct-mttl-lab.service.d}"
COMMIT="${FG_DIRECT_SOURCE_COMMIT:-}"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'Set FG_DIRECT_SOURCE_COMMIT to the tested commit SHA' >&2; exit 1; }
[[ -f "$SERVER_DIR/.env" && -f "$SERVER_DIR/app/database.py" && -f "$LAB_DIR/server/direct_mttl_lab.py" ]] || { echo 'Existing server/lab not found' >&2; exit 1; }
grep -q '# FG_DIRECT_EXTENSION_V1' "$SERVER_DIR/app/main.py" || { echo 'Working Direct extension required first' >&2; exit 1; }
cd "$SERVER_DIR"
docker compose config --quiet
STAGING=$(mktemp -d /tmp/fg-direct-users.XXXXXX)
trap 'rm -rf "$STAGING"' EXIT
BASE="https://raw.githubusercontent.com/nexvary/LinkCore-Android/$COMMIT/server"
for module in direct_mttl.py legacy_direct.py legacy_direct_ui.py legacy_direct_users.py legacy_direct_users_ui.py; do
  curl -fsSL --retry 2 "$BASE/app/$module" -o "$STAGING/$module"
done
curl -fsSL --retry 2 "$BASE/direct_mttl_lab.py" -o "$STAGING/direct_mttl_lab.py"
python3 -m compileall -q "$STAGING"
BACKUP="$SERVER_DIR/direct-users-backup-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -m 700 "$BACKUP"
cp -a "$SERVER_DIR/app" "$BACKUP/app"
cp -a "$LAB_DIR/server/direct_mttl_lab.py" "$BACKUP/daemon.previous.py"
[[ ! -f "$DROPIN_DIR/direct-users.conf" ]] || cp -a "$DROPIN_DIR/direct-users.conf" "$BACKUP/direct-users.previous.conf"
# Snapshot the running SQLite database through sqlite3's consistent backup API.
docker compose exec -T api python - <<'PY'
import os, sqlite3
from app.database import engine
if engine.url.get_backend_name() != 'sqlite':
    raise SystemExit('Expected existing SQLite deployment; stopped before changes')
backup = '/tmp/fg-direct-users-backup.sqlite'
handle = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
os.close(handle)
os.chmod(backup, 0o600)
with sqlite3.connect(engine.url.database) as source, sqlite3.connect(backup) as target:
    source.backup(target)
PY
docker compose cp api:/tmp/fg-direct-users-backup.sqlite "$BACKUP/database.sqlite"
chmod 600 "$BACKUP/database.sqlite"
rollback(){
  trap - ERR
  cp -a "$BACKUP/app/." "$SERVER_DIR/app/"
  install -m 0755 "$BACKUP/daemon.previous.py" "$LAB_DIR/server/direct_mttl_lab.py"
  if [[ -f "$BACKUP/direct-users.previous.conf" ]]; then
    install -m 0644 "$BACKUP/direct-users.previous.conf" "$DROPIN_DIR/direct-users.conf"
  else
    rm -f "$DROPIN_DIR/direct-users.conf"
  fi
  systemctl daemon-reload
  systemctl restart nexvary-direct-mttl-lab || true
  docker compose up -d --build --no-deps api || true
  echo "Update failed; previous code restored. Additive Direct tables retained. Backup: $BACKUP" >&2
  exit 1
}
trap rollback ERR
for module in direct_mttl.py legacy_direct.py legacy_direct_ui.py legacy_direct_users.py legacy_direct_users_ui.py; do
  install -m 0644 "$STAGING/$module" "$SERVER_DIR/app/$module"
done
install -m 0755 "$STAGING/direct_mttl_lab.py" "$LAB_DIR/server/direct_mttl_lab.py"
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN_DIR/direct-users.conf" <<'EOF'
[Service]
StateDirectory=nexvary-direct-mttl
StateDirectoryMode=0700
Environment=NEXVARY_MTTL_ALLOWED_MACS_FILE=/var/lib/nexvary-direct-mttl/allowed-macs.json
EOF
systemctl daemon-reload
systemctl restart nexvary-direct-mttl-lab
docker compose up -d --build --no-deps api
docker compose exec -T api python - <<'PY'
import json, os, time, urllib.request, urllib.error
from app.direct_mttl import adapter
for attempt in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3) as r:
            assert json.load(r)['status'] == 'ok'
        break
    except (OSError, AssertionError):
        if attempt == 29:
            raise
        time.sleep(1)
status = adapter.request('status')
assert status['ok'] and 'allowed_macs' in status, 'Updated daemon not running'
for path in ('/panel/api/direct/users', '/panel/api/direct/devices'):
    request = urllib.request.Request('http://127.0.0.1:8080' + path,
                                    headers={'X-FG-Panel-Token': os.environ['FG_LINK_PANEL_TOKEN']})
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200
try:
    urllib.request.urlopen('http://127.0.0.1:8080/api/v1/direct/devices', timeout=3)
    raise AssertionError('Customer authentication missing')
except urllib.error.HTTPError as error:
    assert error.code == 401
print('Existing API + owner management + protected customer API + multi-MAC daemon: OK')
PY
trap - ERR
printf 'Updated. Open /panel to create users and assign devices. Backup: %s\n' "$BACKUP"
