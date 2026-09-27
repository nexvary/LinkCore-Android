# FG Machines Link Cloud / VPS

This directory contains the deployable cloud backend and web control panel for FG Machines Link.

The design is intentionally **local-first**:

```
MTTL-W01
   │ local TCP 10086
   ▼
FG Machines RCK Android controller
   │ outbound HTTPS only
   ▼
FG Machines RCK Cloud / VPS
   │
   ├── account + Device Sharing
   ├── command relay
   ├── telemetry/history
   └── future Alexa / Google adapters
```

The VPS never talks directly to the MTTL-W01. The Android controller keeps the
verified local protocol and polls the VPS for authorized commands. This avoids
opening the phone's local TCP/HTTP ports to the public Internet.

## Implemented in v0.2.1

- Enterprise Operations Console redesign: fixed operations navigation, compact KPI strip, dense device table, explicit outlet authorization indicators and separated infrastructure provisioning.
- Arabic RTL and English LTR are retained across the new console.
- Cloud service identity and health endpoint now report version 0.2.1.

## Implemented in v0.2

- Responsive bilingual Arabic/English web panel at `/panel`.
- Device and controller overview with online/offline state.
- Browser-based outlet control through the same authenticated cloud command queue.
- Subscriber share management from the panel.
- Per-subscriber outlet authorization. A single four-outlet strip can be split, for example:
  - Subscriber A: outlets 1 + 2
  - Subscriber B: outlets 3 + 4
- Outlet authorization is enforced by the API, not only hidden in the UI.
- Delegated Admin accounts cannot grant outlets outside their own assigned scope.
- One-command Ubuntu/Debian VPS installer: `server/install-vps.sh`.
- Installer generates independent PostgreSQL/JWT/token secrets, keeps PostgreSQL private, starts Docker Compose, and verifies API health.
- Caddy terminates HTTPS automatically after DNS points to the VPS.

## Implemented in v0.1

- Email/password accounts with Argon2 password hashing.
- Short-lived signed JWT access tokens.
- Per-controller high-entropy API key; only its HMAC hash is stored.
- Device claim/registration by MTTL MAC.
- Owner / Admin / Control / View authorization.
- Single-use, expiring Device Sharing invite codes.
- Cloud command queue for outlets 1–4.
- Outbound controller polling with bounded redelivery and command expiry.
- Controller ACK/failed status.
- Controller heartbeat and online/offline state.
- Telemetry upload and history retrieval.
- Voice-intent relay endpoint for future Alexa/Google/mobile adapters.
- Explicit confirmation gate before cloud voice ALL ON.
- Audit log foundation.
- PostgreSQL production storage.
- Caddy automatic HTTPS termination.
- Docker Compose deployment.

## Security boundary

Do **not** expose Android TCP 10086 or local HTTP 18086 to the public Internet.
The controller phone should make outbound HTTPS requests to this service.

Real credentials must never be committed. The public repository contains only
`.env.example`.

## Local development

```bash
cd server
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export FGRCK_ENV=development
export FGRCK_DATABASE_URL=sqlite+pysqlite:///./fg_rck_cloud.db
uvicorn app.main:app --reload --port 8080
```

Open:

- API docs: `http://127.0.0.1:8080/docs`
- Health: `http://127.0.0.1:8080/healthz`

Run tests from the repository root:

```bash
PYTHONPATH=server pytest -q server/tests
```

## VPS deployment

Recommended target: Ubuntu 22.04/24.04 or Debian 12 with a DNS A/AAAA record
already pointing the selected domain to the VPS. Public inbound TCP 80/443 is
required for HTTPS; PostgreSQL remains on the private Docker network.

### One-command installer

From a fresh server:

```bash
curl -fsSL https://raw.githubusercontent.com/nexvary/LinkCore-Android/main/server/install-vps.sh -o /tmp/install-fg-link.sh
sudo bash /tmp/install-fg-link.sh
```

The installer asks for the domain and ACME email, installs Docker/Compose when
needed, clones the project to `/opt/fg-link-cloud`, generates production
secrets, starts the stack and performs a local API health check.

After DNS and TLS are ready:

```text
https://YOUR-DOMAIN/panel
https://YOUR-DOMAIN/healthz
https://YOUR-DOMAIN/docs
```

For a manual deployment, copy `.env.example` to `.env`, replace every
`CHANGE_ME`, then run:

```bash
cd server
docker compose config
docker compose pull
docker compose up -d --build
docker compose ps
```

Caddy obtains and renews the public TLS certificate automatically.

## Android controller integration

The relay is opt-in from the Android UI. The controller phone stores the
one-time controller key in private app preferences and communicates with the VPS
using outbound HTTPS only. Local control remains independent of cloud availability.


The Android controller integration in app version 1.3.7 uses these outbound endpoints:

- `POST /api/v1/controllers/{id}/heartbeat`
- `POST /api/v1/controllers/{id}/telemetry`
- `GET /api/v1/controllers/{id}/commands/poll`
- `POST /api/v1/controllers/{id}/commands/{command_id}/ack`

The controller authenticates using:

```
X-Controller-Key: <controller key>
```

Client/account APIs continue under `/api/v1`. The existing Android
`RemoteApiClient` contract remains compatible for:

- `GET /api/v1/devices`
- `POST /api/v1/devices/{mac}/outlets/{1..4}?state=on|off`
- `GET /api/v1/history/{mac}?hours=24`

The Bearer value for the VPS is an account JWT rather than a LAN sharing token.

## Voice control

`POST /api/v1/voice/intent` is the neutral internal bridge. Alexa/Google
adapters can be added later without changing the MTTL controller protocol.
Vendor account linking/OAuth is not claimed or enabled yet.


## Splitting one strip between two subscribers

The cloud authorization layer supports outlet-scoped access without changing
the verified four-relay MTTL protocol. The owner first shares the device with
each subscriber. After the share code is accepted, open **Subscribers & outlet
access** in `/panel` and save the allowed outlets for each account.

Example:

```text
Subscriber A -> outlets 1, 2
Subscriber B -> outlets 3, 4
Owner        -> outlets 1, 2, 3, 4
```

A denied outlet is rejected with HTTP 403 by the server even if a client tries
to call the command endpoint directly.
