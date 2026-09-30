# FG Link — Home Assistant + voice control

Custom integration 1.1.0. Choose **Direct VPS** or the existing **Android / LAN / ZeroTier** controller. Existing local configuration entries continue to work.

## Install

1. Copy `custom_components/fg_machines_rck` into your Home Assistant **config/custom_components/** directory. Restart Home Assistant (not the VPS).
2. Settings → Devices & services → Add integration → **FG Link**.
3. Choose **Direct VPS**, server `https://link.fgmachines.org`, and a **customer** username/password issued by your FG Link owner panel. Owner Basic Auth credentials are not accepted here.
4. Give that customer the devices/outlets required. Prefer a dedicated integration account so it does not compete with the phone's five-session limit.
5. Each permitted outlet has a switch and power/energy/temperature/state sensors. Rename switches to clear unique names, e.g. “Office lamp”, or “إضاءة المكتب”. Devices added later are discovered during polling.

The integration uses existing authenticated HTTPS customer endpoints; no server update, public admin port, raw TCP client, MQTT broker, or change to strip provisioning is needed. The Direct users extension must already be installed on the VPS.

Commands use explicit ON/OFF, enforce fresh permissions, require `confirmed`, and refresh actual telemetry. A sent/queued/timeout response is not success. Failed POSTs are never automatically retried. Disconnected/stale/unknown/pending/control-disabled or unauthorized switches are unavailable. View-only outlets retain state and telemetry sensors. Session tokens are memory-only; credentials are stored by Home Assistant in its configuration storage for automatic renewal. Protect HA configuration and backups, use a dedicated least-privilege account, and revoke it from the owner panel when removing the integration.

## Voice inside FG Link Android

Install **FG Link Voice 1.6.8** alongside the earlier Direct VPS lab version. This delivery uses a separate package (`com.fgmachines.rck.directvpsvoice`) because the previous transient debug signing key is no longer available; do not uninstall the working app. Production FG Link is unchanged. Sign in, then use the microphone button on the target device card:

- Arabic: `شغّل المخرج الأول`, `اطفي المخرج الثاني`, `اقفل المخرج الرابع`.
- English: `Turn on outlet one`, `Turn off outlet two`.

The card selects the device; speech selects one outlet and one explicit action. Review the MAC/outlet/action confirmation before sending. Negation, multiple targets, toggles and ambiguous text are refused. Speech recognition uses an installed Android recognition provider and may transmit audio to that provider or require Internet; the app does not implement an offline speech engine. If no provider is installed, manual controls remain available. Local modes remain unchanged; this new microphone is on the Direct VPS screen only. No always-listening microphone or wake word is enabled. Custom spoken appliance aliases inside Android are not part of this version.

## Home Assistant Assist

Rename the switch to a unique appliance name, assign an area, then Settings → Voice assistants → **Expose** and explicitly select the permitted switches for Assist. Configure a supported speech-to-text/text-to-speech pipeline in HA and use its mobile app or supported microphone. FG Link supplies switch entities; voice-language support depends on the configured pipeline. Only expose devices intentionally: everyone authorized to use that HA voice assistant can control its exposed entities.

Official instructions: https://www.home-assistant.io/voice_control/voice_remote_expose_devices/

## Google Home / Google Assistant

FG Link switches can be exposed using Home Assistant's existing Google Assistant integration. This is **not a published FG Link “Works with Google Home” service** and no Google account has been linked by this update.

Choose either:

- Home Assistant Cloud: simpler account linking; paid subscription after the trial.
- Manual cloud-to-cloud configuration: an externally reachable HTTPS Home Assistant instance, a Google Home Developer Console project, account linking and private service-account credentials. Follow the official guide; do not point Google's fulfillment/OAuth URLs at FG Link's panel (it is not a Google fulfillment server).

Use `google-assistant.example.yaml` as a starting fragment, replace the project and actual entity IDs, keep private keys in HA's configuration outside Git, and expose only the chosen switches. After account linking, sync devices and test one outlet. Setup applies to that Home Assistant household; it does not enroll all FG Link customers in Google Home automatically.

Official guide: https://www.home-assistant.io/integrations/google_assistant/

## Validation and limits

Adapter/config-flow/coordinator/entity tests run against Home Assistant 2024.12.5 with Python 3.12; current-version live HA and physical voice/Google tests still need your running instance. No Z-Wave support for MTD-01 is added by this integration. Existing MTTL-W01 Direct VPS control remains the transport.

Run: `python -m pytest home_assistant/tests -q` in an environment with Home Assistant, pytest and pytest-asyncio installed.
