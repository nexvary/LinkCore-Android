#!/usr/bin/env bash
# Fresh independent installation from the portable FG Link Panel bundle.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash install.sh' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TARGET="${FGRCK_PANEL_INSTALL_DIR:-/opt/fg-link-panel}"
LAB_TARGET="${FGRCK_PANEL_LAB_DIR:-/opt/nexvary-direct-mttl-lab}"
[[ -f "$SOURCE/app/standalone.py" && -f "$SOURCE/direct_mttl_lab.py" ]] || { echo 'Incomplete installation bundle' >&2; exit 1; }
[[ ! -e "$TARGET" && ! -e "$LAB_TARGET" && ! -e /etc/systemd/system/nexvary-direct-mttl-lab.service ]] || { echo 'Existing installation detected. Use update-existing.sh; nothing overwritten.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'This bundle targets Ubuntu 24.04.' >&2; exit 1; }
DOMAIN="${FGRCK_DOMAIN:-}"
ADMIN="${FGRCK_ADMIN_EMAIL:-}"
[[ -n "$DOMAIN" ]] || read -r -p 'Domain pointing to this VPS: ' DOMAIN
[[ -n "$ADMIN" ]] || read -r -p 'Administrator email: ' ADMIN
python3 - "$DOMAIN" "$ADMIN" <<'PY'
import re,sys
assert re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',sys.argv[1]) and '.' in sys.argv[1], 'Invalid domain'
assert re.fullmatch(r'[a-zA-Z0-9._+%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',sys.argv[2]), 'Invalid administrator email'
PY
PUBLIC_IP="${FGRCK_DIRECT_PUBLIC_IP:-}"
[[ -n "$PUBLIC_IP" ]] || read -r -p 'Public IPv4 for device Controller: ' PUBLIC_IP
python3 - "$PUBLIC_IP" <<'IPCHECK'
import ipaddress,sys
ipaddress.IPv4Address(sys.argv[1])
IPCHECK
# Do not take over ports or replace another running web server.
if ss -ltnH | awk '{print $4}' | grep -Eq ':(80|443|10086)$'; then
 echo 'Port 80, 443 or 10086 is already in use. Installation stopped.' >&2; exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl openssl docker.io docker-compose-v2 python3
systemctl enable --now docker
docker compose version >/dev/null
umask 077
mkdir -p "$TARGET/server" "$LAB_TARGET/server"
cp -a "$SOURCE/app" "$SOURCE/Dockerfile" "$SOURCE/requirements.txt" "$SOURCE/docker-compose.yml" "$SOURCE/Caddyfile" "$TARGET/server/"
cp "$SOURCE/docker-compose.panel.yml" "$TARGET/server/docker-compose.override.yml"
cp "$SOURCE/direct_mttl_lab.py" "$LAB_TARGET/server/"
getent group fgrck-mttl-ipc >/dev/null || groupadd --system fgrck-mttl-ipc
GID=$(getent group fgrck-mttl-ipc | cut -d: -f3)
id nexvary-mttl >/dev/null 2>&1 || useradd --system --home "$LAB_TARGET" --shell /usr/sbin/nologin nexvary-mttl
chmod 0755 "$LAB_TARGET" "$LAB_TARGET/server"
chmod 0644 "$LAB_TARGET/server/direct_mttl_lab.py"
cat > "$TARGET/server/.env" <<EOF
FGRCK_DOMAIN=$DOMAIN
FGRCK_ACME_EMAIL=$ADMIN
FGRCK_ADMIN_EMAIL=$ADMIN
FGRCK_DIRECT_PUBLIC_IP=$PUBLIC_IP
FGRCK_DIRECT_MTTL_GID=$GID
POSTGRES_PASSWORD=$(openssl rand -hex 32)
FGRCK_JWT_SECRET=$(openssl rand -hex 32)
FGRCK_TOKEN_PEPPER=$(openssl rand -hex 32)
FGRCK_SMTP_HOST=
FGRCK_SMTP_PORT=465
FGRCK_SMTP_USER=
FGRCK_SMTP_PASSWORD=
FGRCK_SMTP_FROM=
FGRCK_SMTP_SECURITY=ssl
EOF
openssl rand -hex 16 > "$TARGET/administrator-password.txt"
printf '%s\n' "$ADMIN" > "$TARGET/administrator-email.txt"
cat > /etc/nexvary-direct-mttl-lab.env <<'EOF'
NEXVARY_MTTL_ALLOWED_MAC=
NEXVARY_MTTL_EXPECTED_MODEL=lgutap
NEXVARY_MTTL_POLL_SECONDS=10
NEXVARY_MTTL_ADMIN_PORT=18087
NEXVARY_MTTL_ALLOW_CONTROL=1
NEXVARY_MTTL_MANAGED_REGISTRY=1
EOF
cat > /etc/systemd/system/nexvary-direct-mttl-lab.service <<EOF
[Unit]
Description=FG Link Direct device controller
After=network-online.target
Wants=network-online.target
[Service]
User=nexvary-mttl
Group=fgrck-mttl-ipc
RuntimeDirectory=nexvary-direct-mttl
RuntimeDirectoryMode=0755
StateDirectory=nexvary-direct-mttl
StateDirectoryMode=0700
Environment=NEXVARY_MTTL_ALLOWED_MACS_FILE=/var/lib/nexvary-direct-mttl/allowed-macs.json
Environment=NEXVARY_MTTL_ADMIN_SOCKET=/run/nexvary-direct-mttl/admin.sock
EnvironmentFile=/etc/nexvary-direct-mttl-lab.env
ExecStart=/usr/bin/python3 $LAB_TARGET/server/direct_mttl_lab.py --host 0.0.0.0 --port 10086
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now nexvary-direct-mttl-lab
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
 for port in 80 443 10086; do ufw allow "$port/tcp" >/dev/null; done
fi
cd "$TARGET/server"
docker compose config --quiet
docker compose up -d --build
ready=false
for attempt in $(seq 1 45); do
 if docker compose exec -T api python -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=3)' >/dev/null 2>&1; then ready=true; break; fi
 sleep 2
done
[[ "$ready" == true ]] || { echo 'API health check failed. Inspect: docker compose logs api' >&2; exit 1; }
docker compose exec -T api python -m app.bootstrap_admin < "$TARGET/administrator-password.txt"
printf '%s\n' 'FG_LINK_PANEL_BUNDLE_V1' > "$TARGET/install-marker"
echo "Installed: https://$DOMAIN/panel"
echo "Administrator email: $ADMIN"
echo "Private password file: $TARGET/administrator-password.txt"
echo 'HTTPS needs DNS to point to this server and ports 80/443 reachable.'
echo 'Register each MAC and assign user permissions in the panel before a strip can connect.'
