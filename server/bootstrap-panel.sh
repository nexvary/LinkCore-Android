#!/usr/bin/env bash
# Remote entry point. Download the tested source automatically on the VPS.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run this command with sudo.' >&2; exit 1; }
ACTION="${1:-install}"
[[ "$ACTION" == install || "$ACTION" == update ]] || { echo 'Usage: bootstrap-panel.sh install|update' >&2; exit 1; }
COMMIT="${FG_PANEL_SOURCE_COMMIT:-357b63223f599474a5679f181073d87d845115f5}"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid source commit' >&2; exit 1; }
command -v curl >/dev/null && command -v tar >/dev/null || { echo 'Install prerequisites: sudo apt-get install -y curl tar' >&2; exit 1; }
STAGING=$(mktemp -d /tmp/fg-link-panel.XXXXXX)
trap 'rm -rf "$STAGING"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 "https://github.com/nexvary/LinkCore-Android/archive/$COMMIT.tar.gz" -o "$STAGING/source.tar.gz"
mkdir "$STAGING/source"
tar -xzf "$STAGING/source.tar.gz" --strip-components=1 -C "$STAGING/source"
SOURCE="$STAGING/source/server"
[[ -f "$SOURCE/install-panel.sh" && -f "$SOURCE/update-panel-bundle.sh" ]] || { echo 'Incomplete source archive' >&2; exit 1; }
printf '%s\n' "$COMMIT" > "$SOURCE/BUNDLE_COMMIT"
if [[ "$ACTION" == install ]]; then
  # curl | bash consumes stdin. Collect installer answers from the terminal.
  if [[ -t 1 ]]; then
    bash "$SOURCE/install-panel.sh" </dev/tty
  else
    [[ -n "${FGRCK_DOMAIN:-}" && -n "${FGRCK_ADMIN_EMAIL:-}" && -n "${FGRCK_DIRECT_PUBLIC_IP:-}" ]] || { echo 'Use a terminal, or supply FGRCK_DOMAIN, FGRCK_ADMIN_EMAIL and FGRCK_DIRECT_PUBLIC_IP.' >&2; exit 1; }
    bash "$SOURCE/install-panel.sh"
  fi
else
  bash "$SOURCE/update-panel-bundle.sh"
fi
