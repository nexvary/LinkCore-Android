# Android Direct VPS — owner and customer experiment (1.6.7)

The launcher offers Android / LAN / ZeroTier and Direct VPS. Local controller,
router, one-phone, two-phone, ZeroTier and local API functions remain intact.
Opening Direct VPS from the launcher does not start the Android controller.
This phone communicates over HTTPS; the device communicates directly with the
VPS on TCP 10086. A device has one configured controller address: moving a
Direct device back to a phone requires reprovisioning that address with the
existing setup flow. Existing local devices need no changes.

## Upgrade the already-working server

Use `server/update-direct-users.sh` from an immutable tested commit, with
`FG_DIRECT_SOURCE_COMMIT` set to that same full SHA. The script targets the flat
`/opt/fg-link-server` 0.5 installation. It preserves the existing main.py,
database configuration, Dockerfile, requirements, Compose, .env and Caddyfile.
It snapshots SQLite, backs up the extension and daemon, installs the updated
extension, adds a systemd StateDirectory for the MAC allow-list, restarts the
Direct daemon and rebuilds only the API container. Health, protected owner
routes, customer authentication and daemon version are checked. Failure
restores the old code/drop-in; additive Direct tables remain. Its reported
backup includes the consistent SQLite snapshot. Do not restore the snapshot
over a running server or use the old replacement updater.

There is no server session available to the development environment. Running
the script on the actual VPS and testing new customer accounts remain live
validation steps. The earlier owner browser/Android control was physically
confirmed by the user and is distinct from these new tests.

## Owner: devices and users

Open the existing authenticated `https://link.fgmachines.org/panel`.
The **Direct VPS users and devices** section lets the owner:

1. Register a device's 12-hex MAC before provisioning it. The daemon saves the
   allow-list atomically in `/var/lib/nexvary-direct-mttl/allowed-macs.json`,
   under its service account, mode 0600. Existing approved MACs remain allowed.
2. Create a unique customer username and optional display name. The panel
   generates a strong password and shows it once. Hide the credentials after
   saving/sharing them privately; they are not emailed automatically.
3. Select that customer and device, choose visible outlets and control outlets,
   and save permissions. View-only is the safe default. Control outlets must
   also be visible. A device may be shared with separately scoped users.
4. Revoke a device grant, disable/enable an account, or reset its password.
   Disabling or resetting removes all sessions. Re-enabling does not restore
   old sessions. There is no public self-registration, billing or SaaS flow.

A new device must then have its Controller IP set to `104.207.95.47` using the
existing provisioning procedure and its own Wi-Fi credentials. Registering a
MAC alone does not reconfigure the hardware. Devices still assigned to Android
remain usable locally. Unregistered MACs are rejected at TCP identification.

The owner can additionally set a device-wide control mask through
`PUT /panel/api/direct/registrations/{MAC}/policy` with `control_mask` 0..15.
Every owner's/customer's command intersects this mask. The existing owner's
Basic-auth routes and outlet toggle widget continue to work.

## Customer Android login

Install the isolated experimental APK, package
`com.fgmachines.rck.directvpslab`, label `FG Link Direct VPS`, version
`1.6.7-direct-vps`. It updates the previous experimental APK with the same
signing certificate; it does not replace the production application's identity
or local settings. Debug signing is for this experiment, not production release.

Choose Direct VPS and **Customer account**, enter the HTTPS server and the
username/password issued by the owner. Each customer sees only assigned
hardware and visible outlets. For the owner, choose **Owner / panel
administrator** and use the existing Caddy panel credentials. Never give these
owner credentials to customers.

Each outlet has one state toggle: green ON, crimson OFF, amber pending, gray
offline/unknown. View-only outlets cannot send commands. Online status is the
real Direct TCP session, not an Android heartbeat. Power, energy, temperature
and protection/event fields are shown when available. Only fresh server/device
confirmation yields confirmed; sending alone does not change the relay state.
Timed-out/interrupted commands are not automatically retried. State is fetched
again before further control. Background polling stops when the screen is
hidden. Arabic RTL and English LTR are provided; other locales use English for
this experimental screen.

## API and security boundaries

Owner APIs remain beneath `/panel/api/direct/*`, protected by existing Caddy
Basic Auth and the internal panel token. Cross-origin owner mutations are
rejected. Customer credentials never use owner Basic Auth or the internal token.

Customer endpoints:

- `POST /api/v1/direct/auth/login` with JSON username/password: short-lived
  bearer session (12 hours, at most five live sessions per user).
- `POST /api/v1/direct/auth/logout`: revoke the current session.
- `GET /api/v1/direct/devices`: scoped devices, telemetry and effective policies.
- `POST /api/v1/direct/devices/{MAC}/outlets/{N}?state=on|off`: confirmed/failed/timeout.
- `GET /api/v1/direct/commands/{ID}`: only that user's commands and current grants.

Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Session tokens have
256 bits of random entropy; only SHA256 token digests are stored. Every request
checks account status, token expiry and current grants. Session tokens and
passwords are never saved in Android preferences or audit logs. Only the server
origin, username and selected login mode are remembered. HTTPS validation is
unchanged, redirects are rejected, and the login screen blocks screenshots.
Explicit logout makes a best-effort server revocation; offline/app-process
termination may leave a server session valid until expiry or owner revocation,
while the phone forgets its in-memory credentials.

Customer login/read/command budgets are bounded per API process; the daemon
independently enforces one command per device and a one-second device rate
limit across callers. Audit includes the customer identifier, MAC, outlet,
requested state, time, source and final result. Remote peer information remains
owner-only. The loopback/Unix admin interface is not public. MAC identification
on the original plaintext device protocol is not strong device authentication;
these HTTPS customer accounts do not change that firmware limitation.

## Validation

```sh
gradle --no-daemon --max-workers=2 testDirectVpsLabUnitTest lintDirectVpsLab assembleDirectVpsLab
PYTHONPATH=server python -m pytest server/tests -q
```

Tests cover parsers, real captured telemetry, multi-MAC persistence, duplicate
sessions, offline/timeouts, disabled control, customer isolation, visible
telemetry, view-only and outlet policies, account/session revocation, login rate
limits, command ownership/audit, Android HTTPS/Bearer routing and flat-install
preservation/rollback. On the live system, first grant the already-proven device
to a test customer and verify their own login; only then add other hardware.

## 1.6.8 — voice + Home Assistant

Direct VPS cards now have a speech-recognition button (Arabic/English). It selects one explicit outlet ON/OFF command, displays a confirmation dialog, then uses the existing authenticated command path and real device confirmation. Unsupported/ambiguous/negated commands are not sent. Recognition depends on an installed Android speech provider and may need Internet. This version adds no background listening.

The Home Assistant custom integration now supports customer Direct VPS credentials as well as the existing local phone token. Installation, Assist exposure, and optional Google Home linking instructions are in `home_assistant/README.md`. This is not a published Google cloud service; Google household setup remains required.

## FG Link 2.1 unified release

The unified release retains the official `com.fgmachines.rck` package and release certificate, imports the latest Android 1.6.15 code and adds the Direct VPS screen/voice adapter. Local settings, Android controller modes, and existing voice control remain. Main launcher now selects local or Direct VPS explicitly. The supplied FG Link icon is used in launcher and page headers. Self-service signup remains disabled; owner-issued customer accounts and existing owner login are supported. No VPS upgrade is required for an already installed Direct users extension. Google Home account linking and physical voice verification remain external setup steps.
