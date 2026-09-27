#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${FGRCK_REPO_URL:-https://github.com/nexvary/LinkCore-Android.git}"
INSTALL_DIR="${FGRCK_INSTALL_DIR:-/opt/fg-link-cloud}"
BRANCH="${FGRCK_BRANCH:-main}"

log(){ printf '\n\033[1;36m[FG Link]\033[0m %s\n' "$*"; }
die(){ printf '\n\033[1;31m[FG Link] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }
need_root(){ [ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo bash install-vps.sh"; }
rand(){ openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-56; }

need_root

if [ ! -r /etc/os-release ]; then
  die "Unsupported system. Ubuntu 22.04/24.04 or Debian 12 is recommended."
fi
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) die "This installer currently supports Ubuntu/Debian only (detected: ${ID:-unknown})." ;;
esac

DOMAIN="${FGRCK_DOMAIN:-}"
ACME_EMAIL="${FGRCK_ACME_EMAIL:-}"

if [ -z "$DOMAIN" ]; then
  read -r -p "Domain pointing to this VPS (example: link.example.com): " DOMAIN
fi
if [ -z "$ACME_EMAIL" ]; then
  read -r -p "Email for HTTPS certificate notices: " ACME_EMAIL
fi

[ -n "$DOMAIN" ] || die "Domain is required."
[ -n "$ACME_EMAIL" ] || die "ACME email is required."

log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git openssl docker.io

if ! docker compose version >/dev/null 2>&1; then
  if apt-cache show docker-compose-v2 >/dev/null 2>&1; then
    apt-get install -y docker-compose-v2
  elif apt-cache show docker-compose-plugin >/dev/null 2>&1; then
    apt-get install -y docker-compose-plugin
  else
    apt-get install -y docker-compose
  fi
fi

systemctl enable --now docker

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  die "Docker Compose is unavailable after installation."
fi

log "Preparing application directory: $INSTALL_DIR"
mkdir -p "$(dirname "$INSTALL_DIR")"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
elif [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null || true)" ]; then
  die "$INSTALL_DIR exists and is not an FG Link git checkout."
else
  rm -rf "$INSTALL_DIR"
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR/server"

if [ ! -f .env ]; then
  log "Generating production secrets"
  umask 077
  cat > .env <<EOF
FGRCK_DOMAIN=$DOMAIN
FGRCK_ACME_EMAIL=$ACME_EMAIL
POSTGRES_PASSWORD=$(rand)
FGRCK_JWT_SECRET=$(rand)
FGRCK_TOKEN_PEPPER=$(rand)
FGRCK_JWT_TTL_MINUTES=720
FGRCK_COMMAND_TTL_SECONDS=180
FGRCK_CONTROLLER_ONLINE_SECONDS=90
FGRCK_COMMAND_REDELIVER_SECONDS=30
FGRCK_MAX_COMMAND_ATTEMPTS=5
FGRCK_SIGNED_COMMAND_TTL_SECONDS=120
FGRCK_SIGNED_COMMAND_CLOCK_SKEW_SECONDS=90
FGRCK_SMTP_HOST=
FGRCK_SMTP_PORT=587
FGRCK_SMTP_USER=
FGRCK_SMTP_PASSWORD=
FGRCK_SMTP_FROM=
FGRCK_SMTP_SECURITY=starttls
FGRCK_SMTP_TIMEOUT_SECONDS=10
EOF
  chmod 600 .env
else
  log "Existing .env found; keeping its credentials unchanged"
  sed -i "s|^FGRCK_DOMAIN=.*|FGRCK_DOMAIN=$DOMAIN|" .env
  sed -i "s|^FGRCK_ACME_EMAIL=.*|FGRCK_ACME_EMAIL=$ACME_EMAIL|" .env
fi

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
  log "UFW is active; allowing HTTPS/ACME ports only"
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw allow 443/udp >/dev/null
fi

log "Validating Docker Compose"
"${COMPOSE[@]}" config >/dev/null

log "Building and starting PostgreSQL + FG Link API + Caddy HTTPS"
"${COMPOSE[@]}" pull db caddy
"${COMPOSE[@]}" up -d --build

log "Waiting for the API health check"
healthy=0
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T api python - <<'PY' >/dev/null 2>&1
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=3) as r:
    data=json.loads(r.read().decode())
    assert data.get("ok") is True
PY
  then
    healthy=1
    break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ] || {
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail=120 api
  die "API did not become healthy."
}

log "Deployment complete"
"${COMPOSE[@]}" ps

cat <<EOF

FG Machines Link Cloud 0.3.0 Zero-Trust Relay is running.

Panel:
  https://$DOMAIN/panel

Health:
  https://$DOMAIN/healthz

API documentation:
  https://$DOMAIN/docs

Next:
  1. Open /panel and create your owner account.
  2. Create a Controller and copy its one-time key into the FG Link Android controller.
  3. Register the MTTL device.
  4. Create subscriber share codes.
  5. Open the Android app once so its non-exportable signing key is bound.
  6. Electrical commands are accepted only when signed by that bound phone.

Important:
  - PostgreSQL is not exposed publicly.
  - Android TCP 10086 / local HTTP 18086 must not be opened to the Internet.
  - Keep $INSTALL_DIR/server/.env private and backed up securely.
EOF
