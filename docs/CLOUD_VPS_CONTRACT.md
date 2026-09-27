# FG Machines RCK — Cloud / VPS Contract

FG Machines RCK remains **local-first**. Version 1.3.6 adds a cloud-ready connector,
but a public cloud service is not claimed until an HTTPS VPS/backend is deployed.

## What works before a VPS exists

- Direct MTTL-W01 control through the Android controller on TCP 10086.
- Local automation, Away Mode, runtime history, scenes and diagnostics.
- Device Sharing on the same trusted LAN or private VPN.
- Per-device View / Control / Admin bearer tokens.
- Device Share Codes that carry endpoint + token + role + device scope.
- Local in-app voice commands for the selected connected strip.

## Existing controller API

The Android controller exposes the authenticated API on TCP 18086:

- `GET /api/v1/health`
- `GET /api/v1/devices`
- `POST /api/v1/devices/{mac}/outlets/{1..4}?state=on|off`
- `GET /api/v1/history/{mac}?hours=24`

Authorization uses:

```
Authorization: Bearer <token>
```

A device-scoped token must only return/control its assigned MAC. The controller
returns HTTP 403 if that token tries to access another strip.

## VPS deployment target

When the VPS is available, the first safe deployment path is:

```
FG Machines RCK controller phone
        │
        │ private VPN / outbound tunnel
        ▼
HTTPS VPS / reverse proxy
        │
        ▼
FG Machines RCK client
```

The public side must be HTTPS. Do not expose TCP 18086 directly to the public
Internet.

A later full cloud service can replace the reverse-proxy/tunnel path with an
authenticated relay/account backend while keeping the mobile client API contract
stable.

## Security requirements

- Never commit VPS passwords, private keys, bearer tokens or signing keys.
- TLS terminates on the VPS for public endpoints.
- Device Share Codes are secrets and must be treated like passwords.
- Revoke a share when it is no longer needed.
- Keep device-scoped tokens as the default for family/customer sharing.
- All-device tokens should be reserved for trusted integrations such as a local
  Home Assistant administrator.

## Voice control boundary

Version 1.3.7 uses the Android speech-recognition activity and requests offline
recognition when available. Availability depends on the phone's speech provider.
Voice commands do not require the future FG Machines cloud backend.

Turning on all four outlets requires an explicit confirmation in the app.


## Deployable cloud backend

The repository now includes a deployable VPS backend under `server/`.

Its first production architecture is:

```
MTTL-W01
    │ verified local TCP
    ▼
Android controller
    │ outbound HTTPS only
    ▼
Caddy TLS → FastAPI → PostgreSQL
```

The cloud backend adds account authentication, owner/admin/control/view sharing,
single-use share invites, controller heartbeat, telemetry/history, a bounded
outlet command queue, controller acknowledgements and an internal voice-intent
bridge. The phone's TCP 10086 and local API 18086 remain private and are not
published through the VPS.

See `server/README.md` for deployment and API details.


## Android controller relay (1.3.7)

The controller phone can now sign in to the VPS from the app and explicitly
enable **Cloud controller relay**. When enabled it:

- creates and privately stores a controller ID/key,
- claims the local MTTL-W01 devices for the signed-in owner,
- sends heartbeat and telemetry over outbound HTTPS,
- polls the bounded command queue,
- executes authorized outlet commands through the verified local MTTL protocol,
- acknowledges success/failure back to the VPS.

The relay is disabled by default. Local timers, automation, scenes, alerts and
direct control continue working when the VPS is absent or unreachable.


## Zero-trust device-bound relay (Android 1.6.5 / Cloud 0.3.0)

Remote electrical control now treats the VPS as an untrusted message broker.

Each controller installation creates an ECDSA P-256 key in Android Keystore. The
private key is non-exportable. Its public-key SHA-256 fingerprint is the
installation identity and replaces privacy-sensitive device identifiers such as
IMEI or Android ID.

Every relay command is signed over the exact controller ID, normalized MTTL
MAC, outlet, target state, issue time, expiry, random nonce and installation
fingerprint. The server verifies the signature before queueing, but the Android
controller performs the decisive verification again from its own Keystore key
before calling the MTTL protocol.

Consequences:

- A database/VPS compromise cannot create a new valid ON/OFF command.
- Editing outlet, state, MAC or controller ID invalidates the signature.
- Replays are blocked by short expiry plus a persistent nonce cache.
- Only one active bound phone identity is kept for a controller.
- Replacing the phone rotates the active installation binding.
- The web panel is monitoring/provisioning only for power operations.
- Cloud-side voice command creation is disabled; voice control must become
  signed outlet commands on the trusted Android installation.
- Local device names and room labels are not persisted in the cloud
  registration path.

The VPS still remains capable of denial of service because it transports
messages. Zero-trust signing removes its authority to fabricate executable
electrical commands; it does not make server availability irrelevant.
