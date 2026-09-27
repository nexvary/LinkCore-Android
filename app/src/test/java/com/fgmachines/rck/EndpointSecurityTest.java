package com.fgmachines.rck;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class EndpointSecurityTest {
    @Test public void classifiesLanAsPrivate() throws Exception {
        assertTrue(EndpointSecurity.isPrivateOrVpnEndpoint("http://192.168.1.20:18086"));
    }

    @Test public void classifiesZeroTierStylePrivateAddressAsPrivate() throws Exception {
        assertTrue(EndpointSecurity.isPrivateOrVpnEndpoint("http://10.147.20.8:18086"));
    }

    @Test public void classifiesCgnatOverlayAsPrivate() throws Exception {
        assertTrue(EndpointSecurity.isPrivateOrVpnEndpoint("http://100.90.8.7:18086"));
    }

    @Test public void rejectsPublicAddressAsPrivatePath() throws Exception {
        assertFalse(EndpointSecurity.isPrivateOrVpnEndpoint("https://8.8.8.8"));
    }
}
