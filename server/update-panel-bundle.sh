#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TARGET="${FGRCK_PANEL_INSTALL_DIR:-/opt/fg-link-panel}"
LAB_TARGET="${FGRCK_PANEL_LAB_DIR:-/opt/nexvary-direct-mttl-lab}"
if [[ ! -f "$TARGET/install-marker" ]]; then
  [[ -f "$SOURCE/BUNDLE_COMMIT" ]] || { echo 'Bundle release metadata missing' >&2; exit 1; }
  export FG_DIRECT_SOURCE_COMMIT
  FG_DIRECT_SOURCE_COMMIT=$(cat "$SOURCE/BUNDLE_COMMIT")
  exec bash "$SOURCE/update-direct-users.sh"
fi
[[ $(cat "$TARGET/install-marker") == FG_LINK_PANEL_BUNDLE_V1 ]] || exit 1
cd "$TARGET/server"
docker compose config --quiet
BACKUP="$TARGET/backup-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -m 700 "$BACKUP"
cp -a app Dockerfile requirements.txt .env docker-compose.yml docker-compose.override.yml Caddyfile "$BACKUP/"
cp -a "$LAB_TARGET/server/direct_mttl_lab.py" "$BACKUP/daemon.py"
(umask 077; docker compose exec -T db sh -eu -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/database.pgdump")
[[ -s "$BACKUP/database.pgdump" ]]
docker compose exec -T db pg_restore --list < "$BACKUP/database.pgdump" >/dev/null
rollback(){
 trap - ERR
 cp -a "$BACKUP/app/." app/
 cp -a "$BACKUP/Dockerfile" "$BACKUP/requirements.txt" ./
 cp -a "$BACKUP/daemon.py" "$LAB_TARGET/server/direct_mttl_lab.py"
 systemctl restart nexvary-direct-mttl-lab || true
 docker compose up -d --build --no-deps api || true
 echo "Update failed; previous code restored. Backup: $BACKUP" >&2
 exit 1
}
trap rollback ERR
cp -a "$SOURCE/app/." app/
cp -a "$SOURCE/Dockerfile" "$SOURCE/requirements.txt" ./
cp -a "$SOURCE/direct_mttl_lab.py" "$LAB_TARGET/server/direct_mttl_lab.py"
systemctl restart nexvary-direct-mttl-lab
docker compose up -d --build --no-deps api
ready=false
for attempt in $(seq 1 45); do
 if docker compose exec -T api python -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=3)' >/dev/null 2>&1; then ready=true; break; fi
 sleep 2
done
[[ "$ready" == true ]]
echo "Updated; settings and accounts preserved. Backup: $BACKUP"
