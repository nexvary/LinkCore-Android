# FG Link Matter Bridge — Windows Beta

This is the direct Matter bridge for FG Link. It does **not** require Home Assistant.

```text
Apple Home / Google Home / Alexa / SmartThings / other Matter controller
                          |
                        Matter
                          |
              FG Link Matter Bridge
                          |
             FG Link Local API :18086
                          |
             Android controller phone
                          |
                  MTTL TCP :10086
                          |
                      MTTL-W01
```

Each verified MTTL-W01 contributes four Matter **On/Off Plug-in Unit** endpoints. The bridge reads the device name, room, firmware, online state, outlet labels and relay telemetry from FG Link. Matter commands are sent back only through the authenticated FG Link API.

## First Windows test

1. In FG Link Android, keep the controller service running.
2. Open **Settings → Users, Sharing & Home Assistant** and create a **Home Assistant token**. It is a CONTROL token; despite the label it is also suitable for the Matter bridge.
3. On Windows, extract the CI artifact into a normal folder.
4. Run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\Doctor-FGLink.ps1
   ```
   Verify the phone API and device list first.
5. Install/register the bridge:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\Install-FGLinkMatterBridge.ps1 -ApiUrl http://PHONE_IP:18086
   ```
   Paste the token when prompted.
6. Start it:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\Start-FGLinkMatterBridge.ps1
   ```
7. Open `http://localhost:8283`. Pair the Matterbridge QR/code with the desired Matter controller.
8. Test one outlet OFF/ON first, then all four.

## Network requirements

- Windows and the Matter controller must be able to discover each other on the LAN.
- IPv6 must remain enabled on the Windows network adapter. Internet IPv6 is not required; Matter needs IPv6 on the local network.
- Do not isolate the Windows PC behind a guest/VLAN rule that blocks multicast/mDNS.
- Windows Firewall must allow the Node.js/Matterbridge process on the private network when Windows asks.
- TCP 18086 must be reachable from Windows to the Android controller phone.

## Safety and scope

- Only AC outlets 1–4 are exposed.
- USB 1/2 are intentionally not exposed because independent USB switching is not verified on MTTL-W01.
- Public plain HTTP endpoints are rejected; public remote endpoints require HTTPS.
- The token is stored in the Matterbridge user profile config. Treat it as a credential.
- This is a beta implementation until it passes real commissioning and command tests on the target Windows PC/router/Matter ecosystem.
- Working Matter interoperability is separate from official CSA product certification.

## Windows Server later

The same plugin is designed to run on Windows Server. After the desktop commissioning test is stable, the runtime can be moved to the server and registered as a persistent startup/service task while keeping the same FG Link API contract.
