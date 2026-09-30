package com.fgmachines.rck;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;

public class DeviceGridPolicyTest {
    private static final List<String> FOUR_SAMPLE_MACS = Arrays.asList(
            "2CE032C7102F",
            "2CE032C7A520",
            "88D0391C0C50",
            "D8AA59DC8CF9"
    );

    @Test
    public void fourKnownDevicesUseTwoRows() {
        assertEquals(4, DeviceGridPolicy.visibleCount(FOUR_SAMPLE_MACS.size()));
        assertEquals(2, DeviceGridPolicy.rowCount(FOUR_SAMPLE_MACS.size()));
    }

    @Test
    public void tenDevicesUseExactlyFiveRows() {
        assertEquals(10, DeviceGridPolicy.visibleCount(10));
        assertEquals(5, DeviceGridPolicy.rowCount(10));
    }

    @Test
    public void moreThanTenDevicesNeverOverflowTheGrid() {
        assertEquals(10, DeviceGridPolicy.visibleCount(11));
        assertEquals(5, DeviceGridPolicy.rowCount(11));
    }

    @Test
    public void emptyFleetUsesNoRows() {
        assertEquals(0, DeviceGridPolicy.visibleCount(0));
        assertEquals(0, DeviceGridPolicy.rowCount(0));
    }
}
