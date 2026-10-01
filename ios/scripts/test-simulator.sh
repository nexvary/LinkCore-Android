#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
swift test
xcodegen generate
device_id=$(xcrun simctl list devices available -j | python3 -c 'import sys,json; d=json.load(sys.stdin); print(next(x["udid"] for devices in d["devices"].values() for x in devices if x["name"].startswith("iPhone")))')
xcrun simctl boot "$device_id" 2>/dev/null || true
xcrun simctl bootstatus "$device_id" -b
xcodebuild -project FGLink.xcodeproj -scheme FGLink -destination "platform=iOS Simulator,id=$device_id" -derivedDataPath build -resultBundlePath build/SimulatorTests.xcresult CODE_SIGNING_ALLOWED=NO test
xcrun simctl launch "$device_id" org.fgmachines.fglink
xcrun simctl io "$device_id" screenshot build/iPhone.png
