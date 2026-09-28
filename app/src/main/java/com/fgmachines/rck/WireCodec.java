package com.fgmachines.rck;

/**
 * Runtime-decoded wire constants used by the hardened release.
 *
 * This is not cryptographic secrecy; it prevents the protocol's operational
 * command strings from being exposed as obvious plaintext in a casual APK
 * strings/decompiler pass. R8/obfuscation provides the primary hardening layer.
 */
final class WireCodec {
    private static final int KEY = 0x5A;

    private static final String GET_INFO_ALL = d(47,42,96,61,63,46,51,52,60,53,96,59,54,54);
    private static final String BOOT_PATTERN = d(4,47,42,96,56,53,53,46,51,52,60,53,96,114,1,4,97,6,40,6,52,7,33,107,118,105,104,39,115,97,114,1,106,119,99,27,119,28,59,119,60,7,33,107,104,39,115,97,114,1,106,119,99,27,119,28,59,119,60,7,33,107,104,39,115,97,114,1,4,97,6,40,6,52,7,33,107,118,108,110,39,115,97,57,53,52,52,63,57,46,126);
    private static final String ON_OFF_PATTERN = d(4,47,42,96,114,101,96,63,44,63,52,46,96,115,101,53,52,53,60,60,96,114,1,107,119,110,7,115,96,114,53,52,38,53,60,60,115,126);
    private static final String ON_OFF_PREFIX = d(47,42,96,53,52,53,60,60,96);
    private static final String GET_INFO_PREFIX = d(47,42,96,61,63,46,51,52,60,53,96);
    private static final String IP_PREFIX = d(47,42,96,51,42,96);
    private static final String CONNECT_PREFIX = d(47,42,96,57,53,52,52,63,57,46,96);
    private static final String REBOOT = d(47,42,96,40,63,56,53,53,46,96,106);
    private static final String CRLF = d(87,80);
    private static final String ON = d(53,52);
    private static final String OFF = d(53,60,60);
    private static final String SETUP_PASSWORD_PREFIX = d(22,29,15,5);
    private static final String BOOT_MODEL = d(54,61,47,46,59,42);

    private WireCodec() {}

    static String getInfoAll() { return GET_INFO_ALL; }
    static String bootPattern() { return BOOT_PATTERN; }
    static String onOffPattern() { return ON_OFF_PATTERN; }
    static String onOffPrefix() { return ON_OFF_PREFIX; }
    static String getInfoPrefix() { return GET_INFO_PREFIX; }
    static String ipPrefix() { return IP_PREFIX; }
    static String connectPrefix() { return CONNECT_PREFIX; }
    static String reboot() { return REBOOT; }
    static String crlf() { return CRLF; }
    static String on() { return ON; }
    static String off() { return OFF; }
    static String setupPasswordPrefix() { return SETUP_PASSWORD_PREFIX; }
    static String bootModel() { return BOOT_MODEL; }

    private static String d(int... values) {
        char[] out = new char[values.length];
        for (int i = 0; i < values.length; i++) {
            out[i] = (char) (values[i] ^ KEY);
        }
        return new String(out);
    }
}
