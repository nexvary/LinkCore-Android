package com.fgmachines.rck;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Independent implementation of the publicly documented MTTL local TCP wire format.
 * Frames are UTF-8/ASCII text terminated with CRLF on the controller connection.
 */
public final class MttlProtocol {
    public static final String GET_INFO = WireCodec.getInfoAll();

    private static final Pattern BOOT_INFO = Pattern.compile(
            WireCodec.bootPattern()
    );
    private static final Pattern ON_OFF = Pattern.compile(
            WireCodec.onOffPattern(),
            Pattern.CASE_INSENSITIVE
    );

    private MttlProtocol() {}

    public static String setOutlet(int outlet, boolean on) {
        if (outlet < 1 || outlet > 4) {
            throw new IllegalArgumentException("Outlet index must be 1..4");
        }
        return WireCodec.onOffPrefix() + outlet + ":" + (on ? WireCodec.on() : WireCodec.off());
    }

    public static BootInfo parseBootInfo(String frame) {
        if (frame == null) return null;
        Matcher matcher = BOOT_INFO.matcher(frame.trim());
        if (!matcher.matches()) return null;
        String mac = matcher.group(2).toUpperCase(Locale.US);
        String clientId = matcher.group(3).toUpperCase(Locale.US);
        if (!mac.equals(clientId)) return null;
        return new BootInfo(matcher.group(1), mac, clientId, matcher.group(4));
    }

    public static OutletState parseOnOff(String frame) {
        if (frame == null) return null;
        Matcher matcher = ON_OFF.matcher(frame.trim());
        if (!matcher.matches()) return null;
        int outlet = Integer.parseInt(matcher.group(1));
        boolean on = WireCodec.on().equalsIgnoreCase(matcher.group(2));
        return new OutletState(outlet, on);
    }

    public static Telemetry parseGetInfo(String frame) {
        if (frame == null) return null;
        String trimmed = frame.trim();
        String prefix = WireCodec.getInfoPrefix();
        if (!trimmed.startsWith(prefix)) return null;

        String[] parts = trimmed.substring(prefix.length()).split(":", -1);
        if (parts.length != 8) return null;

        List<OutletTelemetry> outlets = new ArrayList<>(4);
        boolean[] seen = new boolean[5];
        for (int offset = 0; offset < parts.length; offset += 2) {
            Integer channel = parseUnsigned(parts[offset]);
            if (channel == null || channel < 1 || channel > 4 || seen[channel]) return null;

            String[] fields = parts[offset + 1].split(";", -1);
            if (fields.length != 12) return null;

            Integer testState = parseUnsigned(fields[0]);
            Boolean relay = parseBoolean(fields[1]);
            Integer fixedValue = parseUnsigned(fields[2]);
            Boolean overload = parseBoolean(fields[3]);
            Boolean overheat = parseBoolean(fields[4]);
            Integer powerRaw = parseUnsigned(fields[5]);
            Long energyWh = parseHex(fields[6], 8);
            Long previousEnergyWh = parseHex(fields[7], 8);
            Long configuration = parseHex(fields[8], 8);
            Boolean deviceStatus = parseBoolean(fields[9]);
            Long eventCode = parseHex(fields[10], 2);
            Integer temperature = parseSigned(fields[11]);

            if (testState == null || relay == null || fixedValue == null || overload == null
                    || overheat == null || powerRaw == null || energyWh == null
                    || previousEnergyWh == null || configuration == null || deviceStatus == null
                    || eventCode == null || temperature == null) {
                return null;
            }

            seen[channel] = true;
            outlets.add(new OutletTelemetry(
                    channel,
                    relay,
                    overload,
                    overheat,
                    powerRaw,
                    powerRaw / 1000.0,
                    energyWh,
                    energyWh / 1000.0,
                    previousEnergyWh,
                    temperature,
                    deviceStatus,
                    fields[10].toUpperCase(Locale.US),
                    fields[8].toUpperCase(Locale.US),
                    testState,
                    fixedValue
            ));
        }

        if (outlets.size() != 4) return null;
        outlets.sort(Comparator.comparingInt(value -> value.channel));
        return new Telemetry(outlets);
    }

    private static Boolean parseBoolean(String value) {
        if (WireCodec.on().equalsIgnoreCase(value)) return Boolean.TRUE;
        if (WireCodec.off().equalsIgnoreCase(value)) return Boolean.FALSE;
        return null;
    }

    private static Integer parseUnsigned(String value) {
        if (value == null || !value.matches("\\d+")) return null;
        try {
            long parsed = Long.parseLong(value);
            if (parsed > Integer.MAX_VALUE) return null;
            return (int) parsed;
        } catch (NumberFormatException error) {
            return null;
        }
    }

    private static Integer parseSigned(String value) {
        if (value == null || !value.matches("-?\\d+")) return null;
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException error) {
            return null;
        }
    }

    private static Long parseHex(String value, int length) {
        if (value == null || value.length() != length || !value.matches("[0-9A-Fa-f]+")) return null;
        try {
            return Long.parseLong(value, 16);
        } catch (NumberFormatException error) {
            return null;
        }
    }

    public static final class BootInfo {
        public final String model;
        public final String mac;
        public final String clientId;
        public final String firmwareVersion;

        BootInfo(String model, String mac, String clientId, String firmwareVersion) {
            this.model = model;
            this.mac = mac;
            this.clientId = clientId;
            this.firmwareVersion = firmwareVersion;
        }
    }

    public static final class OutletState {
        public final int outlet;
        public final boolean on;

        OutletState(int outlet, boolean on) {
            this.outlet = outlet;
            this.on = on;
        }
    }

    public static final class Telemetry {
        public final List<OutletTelemetry> outlets;

        Telemetry(List<OutletTelemetry> outlets) {
            this.outlets = outlets;
        }
    }

    public static final class OutletTelemetry {
        public final int channel;
        public final boolean relayOn;
        public final boolean overloadProtection;
        public final boolean overheatProtection;
        public final int powerRaw;
        public final double powerW;
        public final long energyWh;
        public final double energyKWh;
        public final long previousEnergyWh;
        public final int temperatureC;
        public final boolean deviceStatus;
        public final String eventCode;
        public final String configurationHex;
        public final int testState;
        public final int fixedValue;

        OutletTelemetry(int channel, boolean relayOn, boolean overloadProtection,
                        boolean overheatProtection, int powerRaw, double powerW,
                        long energyWh, double energyKWh, long previousEnergyWh,
                        int temperatureC, boolean deviceStatus, String eventCode,
                        String configurationHex, int testState, int fixedValue) {
            this.channel = channel;
            this.relayOn = relayOn;
            this.overloadProtection = overloadProtection;
            this.overheatProtection = overheatProtection;
            this.powerRaw = powerRaw;
            this.powerW = powerW;
            this.energyWh = energyWh;
            this.energyKWh = energyKWh;
            this.previousEnergyWh = previousEnergyWh;
            this.temperatureC = temperatureC;
            this.deviceStatus = deviceStatus;
            this.eventCode = eventCode;
            this.configurationHex = configurationHex;
            this.testState = testState;
            this.fixedValue = fixedValue;
        }
    }
}
