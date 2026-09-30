package com.fgmachines.rck;

import android.content.Context;
import android.provider.Settings;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.UUID;

/**
 * Produces a stable, privacy-reduced installation/device fingerprint.
 *
 * ANDROID_ID is scoped by Android to app-signing key + user + device on modern Android,
 * which makes it suitable for the FG Link one-phone/one-account policy without sending
 * the raw identifier to the VPS. A locally generated fallback is used only if needed.
 */
final class VpsDeviceIdentity {
    private static final String PREFS = "fg_rck_device_identity";
    private static final String FALLBACK_ID = "fallback_id";

    private VpsDeviceIdentity() { }

    static String fingerprint(Context context) {
        Context app = context.getApplicationContext();
        String androidId = Settings.Secure.getString(
                app.getContentResolver(), Settings.Secure.ANDROID_ID);
        String source;
        if (androidId != null && !androidId.trim().isEmpty()) {
            source = "android-id|" + app.getPackageName() + "|" + androidId.trim().toLowerCase(Locale.ROOT);
        } else {
            String fallback = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .getString(FALLBACK_ID, "");
            if (fallback == null || fallback.isEmpty()) {
                fallback = UUID.randomUUID().toString();
                app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                        .edit().putString(FALLBACK_ID, fallback).apply();
            }
            source = "fallback|" + app.getPackageName() + "|" + fallback;
        }
        return sha256Hex(source);
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] raw = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(raw.length * 2);
            for (byte b : raw) out.append(String.format(Locale.US, "%02x", b & 0xff));
            return out.toString();
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }
}
