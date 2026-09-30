# Android Direct VPS experiment

The launcher offers Android / LAN / ZeroTier and Direct VPS. The existing local
controller screen and service remain intact. Opening Direct VPS from the launcher
does not initialize the Android controller. The settings screen can reopen the
mode chooser. Existing local controllers may continue independently.
The experimental owner screen supports Arabic RTL and English LTR; other app
languages use English for this screen.

Direct VPS is an **owner-only** native HTTPS client for the deployed FG Link
Server 0.5 panel extension. Use the existing Caddy panel username and password,
not an Android subscriber token. There is no new registration flow.

Default server: `https://link.fgmachines.org`. An optional `/panel` suffix is
accepted. Requests use `/panel/api/direct/devices` and
`/panel/api/direct/devices/{MAC}/outlets/{1..4}?state=on|off`. Basic credentials
are held in memory only, never logged or saved; HTTPS certificate validation is
unchanged, and redirects are rejected. The password field does not enter saved
instance state or autofill. Screenshots are disabled on this owner screen.
Only the server origin and username are remembered. Background polling stops
when the screen is not visible; leaving/destroying the screen clears the login.

Devices and policies come from the existing server registration. The app uses
`connected` from the actual Direct TCP session. Each outlet has one button:
green ON, crimson OFF, amber pending, gray offline or unknown. A tap requests the
inverse of the last retrieved relay state. No optimistic relay state or automatic
command retry is used. `confirmed` means fresh device evidence was received by
the server; failed/timeout/ambiguous delivery are displayed and followed by a
fresh state fetch. Stale state, disabled control, pending commands, and excluded
outlets disable control. The backend remains the authority for policy and audit.

The phone never connects to TCP 10086 or the internal IPC/admin interface. The
original device protocol remains unauthenticated plaintext; HTTPS secures the
owner-to-panel path only.

Build the isolated debug-signed experiment with:

```sh
gradle testDirectVpsLabUnitTest lintDirectVpsLab assembleDirectVpsLab
```

Package: `com.fgmachines.rck.directvpslab`. Label: `FG Link Direct VPS`. This APK
installs alongside the existing production app, without replacing its signing
identity or local configuration. It is not a production release. No VPS update
is needed when the existing legacy Direct panel extension is already installed.

Physical validation: open Direct VPS, enter the panel login, verify the registered
MAC and its current state, then tap each outlet once to turn off and once to turn
on. Check the actual loads and the confirmation text. This Android physical test
must be distinguished from the previously confirmed browser-panel test.
