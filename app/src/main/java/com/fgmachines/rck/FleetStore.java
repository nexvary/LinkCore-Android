package com.fgmachines.rck;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Local-first registry for all MTTL strips known by this controller phone. */
public final class FleetStore {
    private static final String PREFS = "fg_rck_fleet";
    private static final String KEY_MACS = "device_macs";
    private static final String KEY_SELECTED = "selected_mac";
    private static final String PREFIX_NAME = "name_";
    private static final String PREFIX_ROOM = "room_";
    private static final String PREFIX_FIRST_SEEN = "first_seen_";
    private static final String PREFIX_LAST_SEEN = "last_seen_";
    private static final String PREFIX_FW = "firmware_";
    private static final String PREFIX_OUTLET_NAME = "outlet_name_";
    private static final String PREFIX_CLOUD_REF = "cloud_ref_";

    private final SharedPreferences prefs;

    public FleetStore(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public synchronized void register(String mac, String firmware, long seenAt) {
        String key = normalizeMac(mac);
        if (key.isEmpty()) return;
        Set<String> saved = prefs.getStringSet(KEY_MACS, Collections.emptySet());
        java.util.HashSet<String> copy = new java.util.HashSet<>(saved);
        copy.add(key);
        SharedPreferences.Editor editor = prefs.edit()
                .putStringSet(KEY_MACS, copy)
                .putLong(PREFIX_LAST_SEEN + key, seenAt);
        if (prefs.getLong(PREFIX_FIRST_SEEN + key, 0L) == 0L) {
            editor.putLong(PREFIX_FIRST_SEEN + key, seenAt);
        }
        if (firmware != null && !firmware.trim().isEmpty()) {
            editor.putString(PREFIX_FW + key, firmware.trim());
        }
        if (prefs.getString(KEY_SELECTED, "").isEmpty()) editor.putString(KEY_SELECTED, key);
        editor.apply();
    }

    public synchronized void updateLabels(String mac, String name, String room) {
        String key = normalizeMac(mac);
        if (key.isEmpty()) return;
        prefs.edit()
                .putString(PREFIX_NAME + key, clean(name))
                .putString(PREFIX_ROOM + key, clean(room))
                .apply();
    }

    public synchronized void updateOutletName(String mac, int outlet, String name) {
        String key = normalizeMac(mac);
        if (key.isEmpty() || outlet < 1 || outlet > 4) return;
        prefs.edit().putString(PREFIX_OUTLET_NAME + key + "_" + outlet, clean(name)).apply();
    }

    public String outletName(String mac, int outlet) {
        String key = normalizeMac(mac);
        if (key.isEmpty() || outlet < 1 || outlet > 4) return "";
        return prefs.getString(PREFIX_OUTLET_NAME + key + "_" + outlet, "");
    }

    public synchronized void remove(String mac) {
        String key = normalizeMac(mac);
        if (key.isEmpty()) return;
        Set<String> saved = prefs.getStringSet(KEY_MACS, Collections.emptySet());
        java.util.HashSet<String> copy = new java.util.HashSet<>(saved);
        copy.remove(key);
        SharedPreferences.Editor editor = prefs.edit()
                .putStringSet(KEY_MACS, copy)
                .remove(PREFIX_NAME + key)
                .remove(PREFIX_ROOM + key)
                .remove(PREFIX_FW + key)
                .remove(PREFIX_FIRST_SEEN + key)
                .remove(PREFIX_LAST_SEEN + key)
                .remove(PREFIX_CLOUD_REF + key);
        for (int outlet = 1; outlet <= 4; outlet++) {
            editor.remove(PREFIX_OUTLET_NAME + key + "_" + outlet);
        }
        if (key.equalsIgnoreCase(prefs.getString(KEY_SELECTED, ""))) {
            editor.remove(KEY_SELECTED);
        }
        editor.apply();
    }

    public synchronized void select(String mac) {
        String key = normalizeMac(mac);
        if (!key.isEmpty()) prefs.edit().putString(KEY_SELECTED, key).apply();
    }

    public String selectedMac() {
        return normalizeMac(prefs.getString(KEY_SELECTED, ""));
    }

    public DeviceRecord get(String mac) {
        String key = normalizeMac(mac);
        if (key.isEmpty()) return null;
        return new DeviceRecord(
                key,
                prefs.getString(PREFIX_NAME + key, ""),
                prefs.getString(PREFIX_ROOM + key, ""),
                prefs.getString(PREFIX_FW + key, ""),
                prefs.getLong(PREFIX_FIRST_SEEN + key, 0L),
                prefs.getLong(PREFIX_LAST_SEEN + key, 0L)
        );
    }

    public List<DeviceRecord> list() {
        Set<String> macs = prefs.getStringSet(KEY_MACS, Collections.emptySet());
        List<DeviceRecord> out = new ArrayList<>(macs.size());
        for (String mac : macs) {
            DeviceRecord record = get(mac);
            if (record != null) out.add(record);
        }
        out.sort((a, b) -> {
            String ar = a.room.toLowerCase(Locale.ROOT);
            String br = b.room.toLowerCase(Locale.ROOT);
            int roomCompare = ar.compareTo(br);
            if (roomCompare != 0) return roomCompare;
            return a.displayName().compareToIgnoreCase(b.displayName());
        });
        return out;
    }

    public List<String> rooms() {
        java.util.TreeSet<String> rooms = new java.util.TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        for (DeviceRecord record : list()) if (!record.room.isEmpty()) rooms.add(record.room);
        return new ArrayList<>(rooms);
    }

    public synchronized String cloudRef(String mac) {
        String key = normalizeMac(mac);
        if (key.isEmpty()) return "";
        String existing = prefs.getString(PREFIX_CLOUD_REF + key, "");
        if (existing != null && existing.matches("[0-9a-fA-F]{32}")) {
            return existing.toLowerCase(Locale.US);
        }
        String created = java.util.UUID.randomUUID().toString()
                .replace("-", "").toLowerCase(Locale.US);
        prefs.edit().putString(PREFIX_CLOUD_REF + key, created).apply();
        return created;
    }

    public synchronized DeviceRecord findByCloudRef(String cloudRef) {
        if (cloudRef == null || cloudRef.trim().isEmpty()) return null;
        String target = cloudRef.trim();
        for (DeviceRecord record : list()) {
            if (target.equalsIgnoreCase(cloudRef(record.mac))) return record;
        }
        return null;
    }

    public static String normalizeMac(String mac) {
        if (mac == null) return "";
        return mac.replace(":", "").replace("-", "").trim().toUpperCase(Locale.US);
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim();
    }

    public static final class DeviceRecord {
        public final String mac;
        public final String name;
        public final String room;
        public final String firmware;
        public final long firstSeenAt;
        public final long lastSeenAt;

        DeviceRecord(String mac, String name, String room, String firmware,
                     long firstSeenAt, long lastSeenAt) {
            this.mac = mac;
            this.name = name == null ? "" : name;
            this.room = room == null ? "" : room;
            this.firmware = firmware == null ? "" : firmware;
            this.firstSeenAt = firstSeenAt;
            this.lastSeenAt = lastSeenAt;
        }

        public String displayName() {
            return name.isEmpty() ? "MTTL-W01 · " + mac : name;
        }
    }
}
