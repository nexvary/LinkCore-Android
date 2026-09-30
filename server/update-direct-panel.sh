#!/usr/bin/env bash
# Update the existing owner lab + Docker panel without touching main or DB data.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
CLOUD_DIR="${FGRCK_INSTALL_DIR:-/opt/fg-link-cloud}"
BRANCH=private/direct-mttl-lab
MAC="${NEXVARY_MTTL_ALLOWED_MAC:-2CE032C7A520}"
[[ "$MAC" =~ ^[0-9A-Fa-f]{12}$ ]] || { echo 'Invalid MAC' >&2; exit 1; }
MAC="${MAC^^}"
[[ -d "$CLOUD_DIR/.git" && -f "$CLOUD_DIR/server/.env" ]] || {
  echo 'Existing cloud checkout/config not found; set FGRCK_INSTALL_DIR.' >&2; exit 1;
}
[[ $(git -C "$CLOUD_DIR" remote get-url origin) == https://github.com/nexvary/LinkCore-Android.git ]] || {
  echo 'Expected NEXVARY repository origin; stopped.' >&2; exit 1;
}
[[ -z $(git -C "$CLOUD_DIR" status --porcelain --untracked-files=no) ]] || {
  echo 'Checkout contains local edits; stopped without overwriting them.' >&2; exit 1;
}
git -C "$CLOUD_DIR" fetch origin "$BRANCH"
git -C "$CLOUD_DIR" checkout "$BRANCH"
git -C "$CLOUD_DIR" pull --ff-only origin "$BRANCH"
# Preserve secrets; configure only the proven owner device.
python3 - "$MAC" "$CLOUD_DIR/server/.env" <<'PY'
import pathlib, sys, shutil, time
mac, cloud = sys.argv[1:]
for filename, updates in [
    (cloud, {'FGRCK_DIRECT_MTTL_MACS': mac}),
    ('/etc/nexvary-direct-mttl-lab.env', {'NEXVARY_MTTL_ALLOWED_MAC': mac,
                                        'NEXVARY_MTTL_ALLOW_CONTROL': '1'})]:
    path = pathlib.Path(filename)
    content = path.read_text() if path.exists() else ''
    if path.exists():
        shutil.copy2(path, str(path) + '.backup-' + str(time.time_ns()))
    lines = [line for line in content.splitlines() if line.split('=', 1)[0] not in updates]
    path.write_text('\n'.join(lines + [f'{k}={v}' for k,v in updates.items()]) + '\n')
    path.chmod(0o600)
PY
bash "$CLOUD_DIR/server/install-direct-mttl-lab.sh"
GID=$(getent group fgrck-mttl-ipc | cut -d: -f3)
cd "$CLOUD_DIR/server"
export FGRCK_DIRECT_MTTL_GID="$GID"
sed -i "/^FGRCK_DIRECT_MTTL_GID=/d" .env
printf "FGRCK_DIRECT_MTTL_GID=%s\n" "$GID" >> .env
docker compose config --quiet
docker compose up -d --build api
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
