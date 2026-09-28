# FG Link Smart Home Ecosystems — 1.6.9

FG Link keeps the verified MTTL control path and adds interoperable ecosystem bridges around the authenticated local API.

## Routes

| Ecosystem | State | Route |
| --- | --- | --- |
| Home Assistant | Ready | Home Assistant → FG Link API TCP 18086 → MTTL-W01 |
| Amazon Alexa | Ready through Home Assistant | Alexa → Home Assistant → FG Link API |
| Google Home | Ready through Home Assistant | Google Home → Home Assistant → FG Link API |
| Matter | **Windows beta implemented** | Matter controller → FG Link Matter Bridge → FG Link API TCP 18086 → MTTL-W01 |

The Matter bridge source is under `matter_bridge/`. It is a real Matterbridge DynamicPlatform plugin, not a placeholder. It discovers the FG Link fleet from `GET /api/v1/devices`, creates four Matter On/Off Plug-in Unit endpoints per MTTL-W01, mirrors relay state and reachability, and forwards Matter ON/OFF commands to the authenticated FG Link local API.

## Security boundary

The Matter bridge needs a FG Link **CONTROL** token. Plain HTTP is accepted only for loopback, private LAN, link-local, CGNAT/private VPN addresses or `.local` hosts. Public endpoints require HTTPS. The bridge never sends MTTL frames directly and therefore does not bypass the existing controller identity checks.

## MTTL path remains unchanged

- Provisioning endpoint: TCP 30300
- Verified controller protocol: TCP 10086
- Local authenticated integration API: TCP 18086
- Matter bridge: Windows process using Matterbridge/matter.js
- Four verified AC relay channels are exposed. USB switching remains intentionally unavailable.

## Windows beta test

1. On the FG Link Android controller, start the controller service and create a **Home Assistant token**. That token has CONTROL permission and can also be used by the Matter bridge.
2. Keep the Windows PC and Android controller on the same LAN for the first test.
3. Download/extract the `FG-Link-Matter-Bridge-Windows` CI artifact.
4. Run PowerShell in the extracted folder:
   `powershell -ExecutionPolicy Bypass -File .\scripts\Install-FGLinkMatterBridge.ps1 -ApiUrl http://PHONE_IP:18086`
5. Paste the token when prompted. The installer installs the supported Matterbridge runtime if required, registers the local FG Link plugin, and writes the plugin configuration under the current user's Matterbridge profile.
6. Start:
   `powershell -ExecutionPolicy Bypass -File .\scripts\Start-FGLinkMatterBridge.ps1`
7. Open Matterbridge's frontend (normally port 8283), scan its Matter QR code from the chosen Matter ecosystem, and test Outlet 1–4.

## Validation level

The source, TypeScript build, API client tests, Windows packaging and Android regression gates are automated in CI. **Physical Matter commissioning with the user's Windows machine, phone, router and chosen Matter controller remains the final hardware/network validation gate.** Passing CI does not equal CSA certification.
