#!/usr/bin/env bash
set -euo pipefail

BRANCH="${NEXVARY_MTTL_BRANCH:-private/direct-mttl-lab}"
REPO="${NEXVARY_MTTL_REPO:-https://github.com/nexvary/LinkCore-Android.git}"
APP_DIR="/opt/nexvary-direct-mttl-lab"
ENV_FILE="/etc/nexvary-direct-mttl-lab.env"
SERVICE="/etc/systemd/system/nexvary-direct-mttl-lab.service"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

apt-get update
apt-get install -y git python3 ufw

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi

id -u nexvary-mttl >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin nexvary-mttl
chown -R root:root "$APP_DIR"
chmod 0755 "$APP_DIR/server/direct_mttl_lab.py"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
# Fill the 12-hex MAC before the live test if known, for example A1B2C3D4E5F6.
NEXVARY_MTTL_ALLOWED_MAC=
NEXVARY_MTTL_EXPECTED_MODEL=lgutap
NEXVARY_MTTL_POLL_SECONDS=10
NEXVARY_MTTL_ADMIN_PORT=18087

# Keep 0 for the first connectivity/telemetry test.
# Set to 1 only after the strip is positively identified.
NEXVARY_MTTL_ALLOW_CONTROL=0
EOF
  chmod 0600 "$ENV_FILE"
fi

cat > "$SERVICE" <<EOF
[Unit]
Description=NEXVARY Direct MTTL VPS Lab
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nexvary-mttl
Group=nexvary-mttl
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 $APP_DIR/server/direct_mttl_lab.py --host 0.0.0.0 --port 10086
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nexvary-direct-mttl-lab

# TCP 10086 is the controller port used by the strip.
ufw allow 10086/tcp comment 'NEXVARY direct MTTL lab'

echo
echo "NEXVARY direct MTTL lab installed."
echo "Service: systemctl status nexvary-direct-mttl-lab --no-pager"
echo "Logs:    journalctl -u nexvary-direct-mttl-lab -f"
echo "Status:  printf 'status\n' | nc 127.0.0.1 18087"
echo
echo "IMPORTANT: keep NEXVARY_MTTL_ALLOW_CONTROL=0 for the first test."
