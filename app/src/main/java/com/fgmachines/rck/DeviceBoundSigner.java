package com.fgmachines.rck;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyInfo;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Locale;

/**
 * Per-installation signing identity stored in Android Keystore.
 *
 * The private key is generated inside Android Keystore and is never exported.
 * The SHA-256 fingerprint of the X.509 public key is used as the installation
 * identifier instead of IMEI/Android ID.
 */
public final class DeviceBoundSigner {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String ALIAS = "fg_link_zero_trust_signing_v1";
    private static final SecureRandom RANDOM = new SecureRandom();

    public DeviceBoundSigner(Context context) throws Exception {
        // Context is intentionally accepted so callers treat this identity as
        // app-installation state. The key material itself lives in AndroidKeyStore.
        ensureKey();
    }

    public String keyId() throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(publicKey().getEncoded()));
    }

    public String publicKeyBase64() throws Exception {
        return Base64.encodeToString(publicKey().getEncoded(), Base64.NO_WRAP);
    }

    public boolean isHardwareBacked() {
        try {
            PrivateKey privateKey = privateKey();
            KeyFactory factory = KeyFactory.getInstance(privateKey.getAlgorithm(), KEYSTORE);
            KeyInfo info = factory.getKeySpec(privateKey, KeyInfo.class);
            return info.isInsideSecureHardware();
        } catch (Exception ignored) {
            return false;
        }
    }

    public String sign(String canonical) throws Exception {
        Signature signature = Signature.getInstance("SHA256withECDSA");
        signature.initSign(privateKey());
        signature.update(canonical.getBytes(StandardCharsets.UTF_8));
        return Base64.encodeToString(signature.sign(), Base64.NO_WRAP);
    }

    public boolean verifyOwn(String canonical, String signatureBase64) {
        try {
            Signature signature = Signature.getInstance("SHA256withECDSA");
            signature.initVerify(publicKey());
            signature.update(canonical.getBytes(StandardCharsets.UTF_8));
            byte[] raw = Base64.decode(signatureBase64, Base64.DEFAULT);
            return signature.verify(raw);
        } catch (Exception ignored) {
            return false;
        }
    }

    public static String canonical(
            String controllerId,
            String mac,
            int outlet,
            String state,
            long issuedAt,
            long validUntil,
            String nonce,
            String keyId) {
        return String.join("\n",
                "FGLINK-CMD-V1",
                controllerId == null ? "" : controllerId,
                FleetStore.normalizeMac(mac),
                String.valueOf(outlet),
                state == null ? "" : state.toLowerCase(Locale.ROOT),
                String.valueOf(issuedAt),
                String.valueOf(validUntil),
                nonce == null ? "" : nonce,
                keyId == null ? "" : keyId.toLowerCase(Locale.ROOT));
    }

    public static String newNonce() {
        byte[] value = new byte[18];
        RANDOM.nextBytes(value);
        return Base64.encodeToString(
                value, Base64.NO_WRAP | Base64.URL_SAFE | Base64.NO_PADDING);
    }

    private static void ensureKey() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        if (store.containsAlias(ALIAS)) return;

        KeyPairGenerator generator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC, KEYSTORE);
        KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(false)
                .build();
        generator.initialize(spec);
        KeyPair ignored = generator.generateKeyPair();
    }

    private static PrivateKey privateKey() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        KeyStore.Entry entry = store.getEntry(ALIAS, null);
        if (!(entry instanceof KeyStore.PrivateKeyEntry)) {
            throw new IllegalStateException("Device-bound signing key is unavailable");
        }
        return ((KeyStore.PrivateKeyEntry) entry).getPrivateKey();
    }

    private static PublicKey publicKey() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        java.security.cert.Certificate certificate = store.getCertificate(ALIAS);
        if (certificate == null) {
            throw new IllegalStateException("Device-bound signing certificate is unavailable");
        }
        return certificate.getPublicKey();
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            out.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        }
        return out.toString();
    }
}
