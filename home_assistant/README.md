# FG Machines RCK Home Assistant integration

This custom integration uses the authenticated HTTP API exposed by the FG Machines RCK controller phone on port **18086**.

1. In FG Machines RCK, open **Settings → Users, Sharing & Home Assistant**.
2. Tap **Home Assistant token** and copy the token.
3. Note the controller URL displayed by the app, such as `http://192.168.1.2:18086`.
4. Copy `custom_components/fg_machines_rck` into the Home Assistant `config/custom_components/` directory and restart Home Assistant.
5. Add **FG Machines RCK** from **Settings → Devices & services** and enter the URL and token.

Each known MTTL-W01 is represented as a Home Assistant device with four independent switch entities plus total-power, reported-energy and maximum-temperature sensors.

For remote use, prefer a private VPN or HTTPS reverse proxy. Do not expose the phone's plain HTTP port directly to the public internet.


## Alexa and Google Home bridge

FG Link exposes each verified MTTL-W01 outlet to Home Assistant as an independent switch. Once the FG Machines RCK integration is working locally, Home Assistant can expose those switch entities to Amazon Alexa or Google Home using the user's chosen Home Assistant/Alexa/Google integration.

The control route remains:

`Alexa / Google Home → Home Assistant → FG Link API :18086 → MTTL-W01`

FG Link does **not** enable a separate cloud voice-command bypass. The existing cloud `/voice/intent` endpoint remains blocked by the device-bound command policy, so adding voice ecosystems does not weaken the zero-trust relay model.

## Matter

A Matter bridge slot is reserved in the FG Link platform architecture, but it is not advertised as active device support yet. Matter will only be enabled after a concrete bridge implementation passes interoperability and physical-device validation.
