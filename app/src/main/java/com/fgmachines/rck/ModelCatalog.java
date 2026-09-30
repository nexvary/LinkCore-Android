package com.fgmachines.rck;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/**
 * Compatibility signatures for LG U+ / TONLY smart-tap hardware.
 *
 * The catalog intentionally distinguishes the retail model number from KC/safety
 * certificate revisions. Current public certification and reverse-engineering records
 * consistently identify the hardware as MTTL-W01 while showing multiple
 * HU04139-17002* revisions.
 */
public final class ModelCatalog {
    public static final String PRIMARY_MODEL = "MTTL-W01";
    public static final String BOOT_MODEL = WireCodec.bootModel();

    public static final int SETUP_PORT = 30300;
    public static final String SETUP_ADDRESS = "192.168.1.1";
    public static final int CONTROLLER_PORT = 10086;

    private static final List<String> SETUP_PREFIXES = Collections.unmodifiableList(
            Arrays.asList("TONLY_TAP_", "ONLY_TAP_")
    );

    private static final List<String> CERTIFICATE_REVISIONS = Collections.unmodifiableList(
            Arrays.asList(
                    "HU04139-17002A",
                    "HU04139-17002B",
                    "HU04139-17002C",
                    "HU04139-17002D",
                    "HU04139-17002E"
            )
    );

    // Discovery hints only. An OUI match must never be treated as model proof.
    private static final List<String> KNOWN_OUI_PREFIXES = Collections.unmodifiableList(
            Arrays.asList("88:D0:39", "2C:E0:32")
    );

    // Firmware families observed in public local-control projects.
    private static final List<String> KNOWN_FIRMWARES = Collections.unmodifiableList(
            Arrays.asList("1.0.66", "1.0.68", "1.0.106", "1.0.110")
    );

    private ModelCatalog() {}

    public static List<String> setupPrefixes() {
        return SETUP_PREFIXES;
    }

    public static List<String> certificateRevisions() {
        return CERTIFICATE_REVISIONS;
    }

    public static List<String> knownFirmwares() {
        return KNOWN_FIRMWARES;
    }

    public static boolean isSetupSsid(String ssid) {
        if (ssid == null) return false;
        String normalized = ssid.trim().toUpperCase(Locale.US);
        for (String prefix : SETUP_PREFIXES) {
            if (normalized.startsWith(prefix)) return true;
        }
        return false;
    }

    public static String setupPassword(String ssid) {
        if (!isSetupSsid(ssid)) return null;
        String value = ssid.trim();
        int separator = value.lastIndexOf('_');
        if (separator < 0 || separator == value.length() - 1) return null;
        return WireCodec.setupPasswordPrefix() + value.substring(separator + 1);
    }

    public static boolean isCompatibleBootModel(String model) {
        return model != null && BOOT_MODEL.equalsIgnoreCase(model.trim());
    }

    public static boolean isKnownCertificateRevision(String certificate) {
        if (certificate == null) return false;
        for (String revision : CERTIFICATE_REVISIONS) {
            if (revision.equalsIgnoreCase(certificate.trim())) return true;
        }
        return false;
    }

    public static boolean isKnownOui(String mac) {
        if (mac == null) return false;
        String normalized = mac.replace('-', ':').toUpperCase(Locale.US);
        for (String prefix : KNOWN_OUI_PREFIXES) {
            if (normalized.startsWith(prefix)) return true;
        }
        return false;
    }

    /**
     * A capability/signature based family match. This permits future TONLY/LG rebrands
     * using the same protocol to be recognized without pretending an unverified sticker
     * model is already supported.
     */
    public static Compatibility classify(String stickerModel, String bootModel, String setupSsid) {
        if (stickerModel != null && PRIMARY_MODEL.equalsIgnoreCase(stickerModel.trim())) {
            return Compatibility.CONFIRMED_MTTL_W01;
        }
        if (isCompatibleBootModel(bootModel) && (setupSsid == null || isSetupSsid(setupSsid))) {
            return Compatibility.PROTOCOL_FAMILY;
        }
        if (isSetupSsid(setupSsid)) {
            return Compatibility.SETUP_SIGNATURE_ONLY;
        }
        return Compatibility.UNKNOWN;
    }

    public enum Compatibility {
        CONFIRMED_MTTL_W01,
        PROTOCOL_FAMILY,
        SETUP_SIGNATURE_ONLY,
        UNKNOWN
    }
}
