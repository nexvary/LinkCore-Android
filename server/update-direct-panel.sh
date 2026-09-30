#!/usr/bin/env bash
# Update either an existing repository checkout or a flat server installation.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
CLOUD_DIR="${FGRCK_INSTALL_DIR:-/opt/fg-link-server}"
BRANCH=private/direct-mttl-lab
MAC="${NEXVARY_MTTL_ALLOWED_MAC:-2CE032C7A520}"
LAB_ENV="${NEXVARY_MTTL_ENV_FILE:-/etc/nexvary-direct-mttl-lab.env}"
[[ "$MAC" =~ ^[0-9A-Fa-f]{12}$ ]] || { echo 'Invalid MAC' >&2; exit 1; }
MAC="${MAC^^}"
if [[ -f "$CLOUD_DIR/.env" && -f "$CLOUD_DIR/docker-compose.yml" ]]; then
  SERVER_DIR="$CLOUD_DIR"
  FLAT=1
elif [[ -f "$CLOUD_DIR/server/.env" && -f "$CLOUD_DIR/server/docker-compose.yml" && -d "$CLOUD_DIR/.git" ]]; then
  SERVER_DIR="$CLOUD_DIR/server"
  FLAT=0
else
  echo 'Existing server .env/docker-compose.yml not found; set FGRCK_INSTALL_DIR.' >&2
  exit 1
fi
if [[ "$FLAT" == 1 ]] && grep -q 'from .database import' "$SERVER_DIR/app/main.py" && grep -q 'FG_LINK_PANEL_TOKEN' "$SERVER_DIR/app/main.py"; then
  echo 'Detected deployed FG Link Server 0.5. Use install-legacy-direct-extension.sh; this updater will not replace that API.' >&2
  exit 1
fi
cd "$SERVER_DIR"
# No credentials or expanded Compose configuration are printed.
docker compose config --services | grep -qx api || { echo 'Expected existing api service; stopped.' >&2; exit 1; }
OVERRIDE="$SERVER_DIR/docker-compose.override.yml"
if [[ -e "$OVERRIDE" ]] && ! grep -q '^# FG Link Direct VPS managed override$' "$OVERRIDE"; then
  echo 'Existing custom Compose override found; stopped without replacing it.' >&2
  exit 1
fi
BACKUP="$SERVER_DIR/direct-backup-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -m 700 "$BACKUP"
for item in app requirements.txt Dockerfile docker-compose.yml docker-compose.override.yml .env; do
  if [[ -e "$SERVER_DIR/$item" ]]; then cp -a "$SERVER_DIR/$item" "$BACKUP/"; fi
done
if [[ "$FLAT" == 1 ]]; then
  STAGING=$(mktemp -d /tmp/fg-direct-source.XXXXXX)
  trap 'rm -rf "$STAGING"' EXIT
  git clone --depth 1 --single-branch --branch "$BRANCH" https://github.com/nexvary/LinkCore-Android.git "$STAGING/repo"
  SOURCE_SERVER="$STAGING/repo/server"
  # Overlay application code only. Retain site, Compose project, secrets and DB volumes.
  cp -a "$SOURCE_SERVER/app/." "$SERVER_DIR/app/"
  cp "$SOURCE_SERVER/requirements.txt" "$SERVER_DIR/"
else
  [[ $(git -C "$CLOUD_DIR" remote get-url origin) == https://github.com/nexvary/LinkCore-Android.git ]] || { echo 'Expected NEXVARY origin; stopped.' >&2; exit 1; }
  [[ -z $(git -C "$CLOUD_DIR" status --porcelain --untracked-files=no) ]] || { echo 'Tracked local edits found; stopped.' >&2; exit 1; }
  git -C "$CLOUD_DIR" fetch origin "$BRANCH"
  git -C "$CLOUD_DIR" checkout "$BRANCH"
  git -C "$CLOUD_DIR" pull --ff-only origin "$BRANCH"
  SOURCE_SERVER="$CLOUD_DIR/server"
fi
python3 - "$MAC" "$SERVER_DIR/.env" "$LAB_ENV" <<'PY'
import pathlib, sys, shutil, time
mac, cloud, lab = sys.argv[1:]
for filename, updates in [
    (cloud, {'FGRCK_DIRECT_MTTL_MACS': mac}),
    (lab, {'NEXVARY_MTTL_ALLOWED_MAC': mac, 'NEXVARY_MTTL_ALLOW_CONTROL': '1'})]:
    path = pathlib.Path(filename)
    content = path.read_text() if path.exists() else ''
    if path.exists():
        shutil.copy2(path, str(path) + '.backup-' + str(time.time_ns()))
    lines = [line for line in content.splitlines() if line.split('=', 1)[0] not in updates]
    path.write_text('\n'.join(lines + [f'{k}={v}' for k,v in updates.items()]) + '\n')
    path.chmod(0o600)
PY
bash "$SOURCE_SERVER/install-direct-mttl-lab.sh"
GID=$(getent group fgrck-mttl-ipc | cut -d: -f3)
[[ "$GID" =~ ^[0-9]+$ ]] || { echo 'IPC group not found' >&2; exit 1; }
sed -i '/^FGRCK_DIRECT_MTTL_GID=/d' "$SERVER_DIR/.env"
printf 'FGRCK_DIRECT_MTTL_GID=%s\n' "$GID" >> "$SERVER_DIR/.env"
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
cd "$SERVER_DIR"
docker compose config --quiet
docker compose up -d --build --no-deps api
systemctl is-active --quiet nexvary-direct-mttl-lab
docker compose exec -T api python - <<'PY'
import json, urllib.request, time
from app.direct_mttl import adapter
assert adapter.request('status')['ok']
for attempt in range(15):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3) as response:
            assert json.load(response)['ok']
        break
    except OSError:
        if attempt == 14:
            raise
        time.sleep(1)
print('Direct IPC + API health OK. Open /panel and test the registered owner device.')
PY
printf 'Update completed. Previous application/config backup: %s\n' "$BACKUP"
