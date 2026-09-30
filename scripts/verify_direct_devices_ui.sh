#!/usr/bin/env bash
set -Eeuo pipefail
PKG=com.fgmachines.rck.debug
APK="${1:?debug APK required}"
OUT="${2:-direct-ui-validation}"
mkdir -p "$OUT"
adb install -r "$APK"
for page in direct_devices local_devices settings dashboard; do
  adb shell am force-stop "$PKG"
  adb shell run-as "$PKG" rm -f files/fg_ui_gate_state files/fg_ui_capture.png
  adb shell am start -W -n "$PKG/com.fgmachines.rck.MainActivity" --es fg_ui_test_page "$page"
  ready=false
  for attempt in $(seq 1 25); do
    marker=$(adb shell run-as "$PKG" cat files/fg_ui_gate_state 2>/dev/null | tr -d '\r' || true)
    if [[ "$marker" == "$page" ]]; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { adb logcat -d -s AndroidRuntime FGLinkUiGate; exit 1; }
  adb exec-out run-as "$PKG" cat files/fg_ui_capture.png > "$OUT/$page.png"
  adb shell uiautomator dump /sdcard/direct-ui.xml >/dev/null
  adb pull /sdcard/direct-ui.xml "$OUT/$page.xml" >/dev/null
 done
