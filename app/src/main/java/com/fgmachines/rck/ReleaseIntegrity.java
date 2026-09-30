package com.fgmachines.rck;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Release-origin check for the public APK.
 *
 * This is one defense-in-depth layer, not a claim that Android packages cannot
 * be reverse engineered. It makes simple re-sign/repackage copies fail closed.
 */
public final class ReleaseIntegrity {
    private static final String OFFICIAL_PACKAGE = "com.fgmachines.rck";
    private static final String OFFICIAL_CERT_SHA256 =
            "b9ca4a23be53f161a47b5aaf97023d2bbbeebdaf671337d2466fb74cc1f29fdf";

    private ReleaseIntegrity() {}

    public static void enforce(Context context) {
        if (!isTrusted(context)) {
            throw new SecurityException("FG Link release integrity check failed");
        }
    }

    public static boolean isTrusted(Context context) {
        if (!BuildConfig.RELEASE_INTEGRITY_ENFORCED) return true;
        if (context == null || !OFFICIAL_PACKAGE.equals(context.getPackageName())) return false;

        try {
            PackageManager pm = context.getPackageManager();
            PackageInfo info;
            Signature[] signatures;

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info = pm.getPackageInfo(context.getPackageName(),
                        PackageManager.GET_SIGNING_CERTIFICATES);
                if (info.signingInfo == null) return false;
                signatures = info.signingInfo.hasMultipleSigners()
                        ? info.signingInfo.getApkContentsSigners()
                        : info.signingInfo.getSigningCertificateHistory();
            } else {
                info = pm.getPackageInfo(context.getPackageName(),
                        PackageManager.GET_SIGNATURES);
                signatures = info.signatures;
            }

            if (signatures == null || signatures.length == 0) return false;
            for (Signature signature : signatures) {
                if (constantTimeEquals(OFFICIAL_CERT_SHA256, sha256(signature.toByteArray()))) {
                    return true;
                }
            }
            return false;
        } catch (PackageManager.NameNotFoundException | RuntimeException error) {
            return false;
        }
    }

    private static String sha256(byte[] value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value);
            char[] hex = new char[digest.length * 2];
            final char[] alphabet = "0123456789abcdef".toCharArray();
            for (int i = 0; i < digest.length; i++) {
                int b = digest[i] & 0xff;
                hex[i * 2] = alphabet[b >>> 4];
                hex[i * 2 + 1] = alphabet[b & 0x0f];
            }
            return new String(hex);
        } catch (NoSuchAlgorithmException error) {
            return "";
        }
    }

    private static boolean constantTimeEquals(String expected, String actual) {
        if (expected == null || actual == null || expected.length() != actual.length()) return false;
        int diff = 0;
        for (int i = 0; i < expected.length(); i++) {
            diff |= expected.charAt(i) ^ actual.charAt(i);
        }
        return diff == 0;
    }
}
