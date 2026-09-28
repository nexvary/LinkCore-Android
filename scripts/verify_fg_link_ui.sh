#!/usr/bin/env bash
set -euo pipefail

APP_PACKAGE="com.fgmachines.rck.sidecar163"
APP_ACTIVITY="$APP_PACKAGE/com.fgmachines.rck.MainActivity"

wake_and_unlock() {
  adb shell input keyevent KEYCODE_WAKEUP || true
  adb shell wm dismiss-keyguard || true
  adb shell input keyevent 82 || true
  adb shell settings put system screen_off_timeout 2147483647 || true
  adb shell am broadcast -a android.intent.action.CLOSE_SYSTEM_DIALOGS >/dev/null 2>&1 || true
}

adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
  sleep 2
done

adb install -r apk-debug/app-debug.apk
adb install -r apk-sidecar/app-sidecar.apk
adb shell pm list packages | grep -E 'com.fgmachines.rck.debug|com.fgmachines.rck.sidecar163'

capture_page() {
  local request="$1"
  local expected="$2"
  local output="$3"

  adb shell am force-stop "$APP_PACKAGE" || true
  adb shell run-as "$APP_PACKAGE" rm -f files/fg_ui_gate_state files/fg_ui_capture.png >/dev/null 2>&1 || true
  wake_and_unlock
  adb shell am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
    -n "$APP_ACTIVITY" --es fg_ui_test_page "$request" >/dev/null

  local attempt=1
  local marker=""
  while [ "$attempt" -le 60 ]; do
    marker="$(adb shell run-as "$APP_PACKAGE" cat files/fg_ui_gate_state 2>/dev/null | tr -d '\r\n' || true)"
    if [ "$marker" = "$expected" ]; then
      break
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  if [ "$marker" != "$expected" ]; then
    echo "UI capture failed: expected marker '$expected', got '$marker' for request '$request'" >&2
    adb logcat -d -t 1200 | grep -E "$APP_PACKAGE|FGLinkUiGate|AndroidRuntime|FATAL EXCEPTION|ANR" | tail -n 250 || true
    exit 1
  fi

  adb exec-out run-as "$APP_PACKAGE" cat files/fg_ui_capture.png > "$output"
  test -s "$output"
  local size
  size="$(stat -c%s "$output")"
  if [ "$size" -lt 30000 ]; then
    echo "UI capture failed: $output is unexpectedly small ($size bytes)" >&2
    exit 1
  fi
  echo "Captured $output ($size bytes)"
}

# Every image below is rendered by the actual 1.6.8 sidecar APK's Android
# view hierarchy, not a mockup and not the hosted emulator framebuffer.
capture_page dashboard       dashboard       FG-Link-1.6.8-dashboard.png
capture_page setup           setup           FG-Link-1.6.8-setup.png
capture_page scan            scan            FG-Link-1.6.8-scan.png
capture_page settings        settings        FG-Link-1.6.8-settings.png
capture_page subscriber      subscriber      FG-Link-1.6.8-subscriber.png
capture_page about           about           FG-Link-1.6.8-about.png
capture_page remote_ac       remote-ac       FG-Link-1.6.8-remote-ac.png
capture_page remote_fan      remote-fan      FG-Link-1.6.8-remote-fan.png
capture_page diagnostics     diagnostics     FG-Link-1.6.8-diagnostics.png
capture_page network_doctor  network-doctor  FG-Link-1.6.8-network-doctor.png

echo "FG Link complete real-page screenshot gallery passed."
