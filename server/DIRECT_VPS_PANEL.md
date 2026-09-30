# Direct VPS experimental panel integration

Work branch: `private/direct-mttl-lab`. Android/LAN signed endpoints are unchanged.
The repository is public; the branch name does not provide privacy.

The existing registered device is selected by `FGRCK_DIRECT_MTTL_MACS` (comma-separated
12-hex MACs). An unregistered session never creates a user/device or grants access.
The device retains its existing controller foreign key for compatibility; direct
commands are explicitly excluded from Android command polling.

The panel API uses `app/direct_mttl.py`, with bounded JSON line IPC. Docker uses
`/run/nexvary-direct-mttl/admin.sock`, mounted read-only and accessible via supplemental
GID 19087. The installer creates group `fgrck-mttl-ipc`, socket mode 0660, and the
systemd runtime directory. Non-container API deployments can use loopback 18087
by leaving `FGRCK_DIRECT_MTTL_SOCKET` empty. No admin listener is exposed publicly.

Run `sudo bash server/update-direct-panel.sh` from the checked-out branch on the VPS.
It supports the existing flat server installation at `/opt/fg-link-server`
and repository layouts with `server/.env` (override with `FGRCK_INSTALL_DIR`), preserves and backs up credentials, enables control only for
the configured test MAC, updates the lab service and rebuilds the existing API.
For flat installs it stages source separately, backs up the previous application,
overlays application/dependency/image files, and adds a managed Compose override.
It preserves the original Compose/Caddy configuration, project identity and database
volumes. An existing custom Compose override stops the update before changes.
Repository installs stop if tracked local changes exist.
The existing registered owner device must have MAC `2CE032C7A520`; registration is
still required. This deployment script has not been tested on the physical VPS.

`POST /api/v1/devices/{mac}/direct-outlets/{1..4}?state=on|off` requires JWT,
control role and the existing OutletPolicy. Database status moves queued → sent →
confirmed/failed/timeout, with audit records and fresh device event/telemetry confirmation.
Here `sent` records IPC dispatch intent; only `confirmed` establishes device feedback.
A request interrupted by an API crash becomes timeout on the next command-status read.
No automatic retry of electricity commands occurs after unknown outcomes.

The daemon serializes commands per MAC, limits them to one per second, bounds
confirmation to 8 seconds, closes idle/unidentified sessions and supersedes duplicate
sessions safely. A stale cached relay value cannot confirm a new command.

The panel shows current sessions, model/firmware/peer/timestamps, outlet states,
power/energy/temperature/protection fields when available. Unknown firmware fields
remain unavailable instead of being invented. Current direct telemetry is served from
session state; it is not copied into historical Android telemetry snapshots.

The existing parser fixtures in `tests/test_direct_mttl_lab.py` represent the available
MTTL capture format. Firmware extras, partial outlet sets, trailing delimiters and missing
optional fields are tolerated. No new physical capture was available in this session.

TCP 10086 is the device's unauthenticated plaintext protocol. MAC filtering limits
accidental access but cannot authenticate against MAC impersonation; this is an owner
experiment, not device-level Zero Trust. HTTPS/JWT protects the panel side.

Validation: `PYTHONPATH=server python -m pytest server/tests -q`.
After deployment, inspect the DIRECT VPS badge and physically verify ON/OFF.
