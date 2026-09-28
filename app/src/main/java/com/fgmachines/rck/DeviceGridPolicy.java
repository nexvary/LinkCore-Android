package com.fgmachines.rck;

/** Pure layout policy for the My Devices 2x5 grid. */
final class DeviceGridPolicy {
    static final int MAX_DEVICES = 10;
    static final int COLUMNS = 2;

    private DeviceGridPolicy() { }

    static int visibleCount(int totalDevices) {
        return Math.max(0, Math.min(MAX_DEVICES, totalDevices));
    }

    static int rowCount(int totalDevices) {
        int visible = visibleCount(totalDevices);
        return (visible + COLUMNS - 1) / COLUMNS;
    }
}
