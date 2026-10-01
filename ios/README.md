# FG Link for iOS — development port

Native SwiftUI project based on the **FG Link Android 2.1.2 / build 47** release.
The application uses the approved FG Link icon, FG Machines attribution and official developer links.

Reference Android source: `release/fg-link-2.1`, commit `fa017acaddec14a7b27c081ea3f27d3c66bde11b`.
Reference APK SHA-256: `07c9307f9657b02c6893174a37f2a60701b0afae4c30985877599cc5abfeff0f`.
The Android package remains `com.fgmachines.rck`; the separate iOS bundle identifier is `org.fgmachines.fglink`.

## تشغيل المحاكي على ماك

ثبّت Xcode وأحد محاكيات iPhone من إعداداته، ثم شغّل من جذر المستودع:

```bash
brew install xcodegen
bash ios/scripts/test-simulator.sh
```

السكربت يبني مكتبة البروتوكول، ثم يولّد مشروع Xcode ويشغّل اختبارات اتصال TCP واختبارات الواجهة. تحفظ النتائج ولقطة الشاشة داخل `ios/build`.

لفتح المشروع يدويًا:

```bash
cd ios
xcodegen generate
open FGLink.xcodeproj
```

اختر محاكي iPhone ثم Run. ملفات `Info.plist` وentitlements والمشروع تُولّد من `project.yml`.

## Connection routes

| Route | Behavior |
| --- | --- |
| Local / LAN | The strip initiates its normal TCP connection to the phone on port 10086. A valid `lgutap` boot frame with matching MAC/client identity is required before control. |
| LAN / VPN | Imports the Android `FGRCK1` share code and talks to the existing controller API. Only numeric private/loopback/link-local/CGNAT addresses are accepted. Configure ZeroTier or another VPN separately. |
| Direct VPS | Subscriber-only HTTPS login, scoped device list, per-outlet permissions, confirmed commands and server email settings. There is no owner login or self-service account registration in the iOS app. |

Local control stops when iOS suspends the app. Use the VPS or an independently running controller for control independent of the iPhone's foreground state. The app never silently rewrites a strip's controller to switch transport.

## Implemented behavior

- Arabic RTL and English LTR, immediate language switching, navigation back buttons and a responsive two-column strip grid.
- Four verified AC channels. USB charging ports are described without invented channel 5/6 switching commands.
- Reported relay state, power, energy and temperature; unknown measurements remain unknown.
- No optimistic relay success. Local commands wait for firmware acknowledgement or telemetry, private API commands poll actual state, and VPS commands require `confirmed`.
- One pending command per device, permission gating, offline handling and bounded protocol/HTTP response parsing.
- Setup Wi-Fi password derivation, automatic joining through `NEHotspotConfiguration`, manual joining and text-dialect provisioning on `192.168.1.1:30300`.
- VPS IPv4 resolution before joining the setup AP. Network configuration does not create account grants; an administrator must assign the strip to the subscriber.
- Speech recognition through Apple's APIs, narrow Arabic/English command grammar and explicit review/confirmation before sending.
- Server email settings, thresholds, save and test operations. The VPS must already have functioning SMTP configuration.
- Session-only history from received power measurements and official About links.
- HTTPS validation, no credential-bearing redirects, in-memory session credentials, no password/share-token persistence and no embedded signing keys.

## Tests and distribution

The Swift package has ten core tests covering identity, permissions, stream fragmentation, telemetry, setup injection, voice ambiguity, private-network boundaries, HTTP framing and the VPS session contract.

`IntegrationTests` exercises the Network framework using a simulated strip over a real loopback TCP connection. Its port is isolated from the app's normal controller. `UITests` checks Arabic/English switching, subscriber login, setup consent and About, and retains screenshot attachments.

The `FG Link iOS` GitHub Actions workflow uses a macOS runner. The result bundle and unsigned simulator `.app` are development artifacts. They are **not** an installable iPhone IPA.

For physical-device development, choose a signing team in Xcode and enable Hotspot Configuration for the app identifier. App Store/TestFlight distribution requires the corresponding Apple signing and distribution setup. Android JKS signing keys cannot sign an iOS application.

## Remaining verification and parity

This port is not yet a full Android feature-parity release.

| Item | Remaining work |
| --- | --- |
| Real MTTL hardware on iPhone | Check local-network permission, reconnection, command acknowledgements and telemetry against the actual strip. |
| Wi-Fi provisioning | Test automatic/manual join, router credentials, VPS resolution and post-reboot return to home Wi-Fi on a physical iPhone. The simulator cannot validate radio behavior. |
| Speech | Verify Arabic/English microphone capture and availability of on-device language models on physical hardware. |
| ZeroTier | Verify the actual iOS VPN routing and controller address with the user's network. |
| Home Assistant / Google Home | Existing server integrations are retained in the repository; this app does not implement an additional iOS integration setup wizard. |
| Timers, scenes, Away Mode, persistent analytics | Not ported. Background automation should be hosted on an independent controller/server before claiming Android-equivalent reliability. |
| Appliance IR remotes and Z-Wave | Android driver/remote screens are not ported. iOS requires a compatible external bridge and a verified adapter contract. |
| Diagnostics and USB discovery | Android diagnostic catalogs and passive USB-discovery tooling are not ported. |
| Signed distribution | No distribution certificate, provisioning profile or signed IPA is included. |

The privacy manifest declares account identifiers, email and device telemetry for app functionality, with no advertising tracking. Local settings use the app's own UserDefaults. Confirm the deployed service's privacy disclosures before store distribution.

All original project licensing and attribution in the repository's `LICENSE` continue to apply.
