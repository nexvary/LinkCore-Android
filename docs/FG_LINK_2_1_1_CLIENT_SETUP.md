# FG Link 2.1.1 — customer-only Direct VPS and strip setup

Package: `com.fgmachines.rck`; versionCode: `46`.

The Android Direct VPS client authenticates personal accounts at `/api/v1/direct` only. Owner login, Basic authentication, owner API routes and the account-type selector have been removed. Owner management stays in the protected web panel. On upgrade, an old owner selection and its remembered username are removed without clearing local settings or devices.

Use **إعداد مشترك / Set up power strip** from the connection chooser, local home, or Direct VPS screen. The wizard reuses `MttlProvisioner`, Android Wi-Fi permissions and the existing VPS IPv4 resolver. Choose local or Direct VPS inside the wizard. Local starts with the saved Controller address without changing the saved address. Direct prepares the server IPv4 while Internet is available; no manual server IP is required. Automatic and manual setup-AP paths are available. The wizard does not start an Android controller or register/assign any MAC.

For a new strip, enter the setup SSID and destination router Wi-Fi, acknowledge the network-setting change, configure, then return to Internet. The first result reports the device's setup response, not a confirmed VPS connection. Direct then polls only the personal account's assigned devices: online, assigned but offline, or absent/request administration approval. The suffix used for this visual check never authorizes control. All device and outlet grants remain server-enforced. Voice commands use the same control restrictions.

Already connected strips require no setup. Install the signed release as an update; do not uninstall or clear app data.

## Validation

- Android JVM suite: 105 tests, zero failures/errors/skips.
- Release Lint and optimized release build passed.
- Legacy Direct panel/customer API suite: 12 tests passed, including a customer knowing a MAC being unable to register or grant it, and an assigned device becoming visible only after panel approval.
- Broader server suite: 42 tests passed before adding the new test; the Unix-socket integration test could not run because this execution environment denies AF_UNIX sockets.
- Signing uses the provided original release keystore; package/version and signing certificate are verified after signing.
- Physical setup AP, router return, LAN/ZeroTier connectivity and on-device upgrade still require hardware verification. No physical strip was connected to this environment. Emulator UI/installation verification was unavailable here.

## Rebuild

Use JDK 17, Android SDK 35 and Gradle 8.9+. Run `gradle testDebugUnitTest lintRelease assembleRelease`. Supply the existing `FG_RCK_KEYSTORE_PATH`, `FG_RCK_KEYSTORE_PASSWORD`, `FG_RCK_KEY_ALIAS`, and `FG_RCK_KEY_PASSWORD` environment variables for signing. Keep all key material outside the repository.
