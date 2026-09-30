package com.fgmachines.rck;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class SmartHomeEcosystemCatalogTest {
    @Test
    public void homeAssistantAlexaAndGoogleRoutesAreReady() {
        assertTrue(SmartHomeEcosystemCatalog.isReady(
                SmartHomeEcosystemCatalog.Ecosystem.HOME_ASSISTANT));
        assertTrue(SmartHomeEcosystemCatalog.isReady(
                SmartHomeEcosystemCatalog.Ecosystem.AMAZON_ALEXA));
        assertTrue(SmartHomeEcosystemCatalog.isReady(
                SmartHomeEcosystemCatalog.Ecosystem.GOOGLE_HOME));
        assertEquals(3, SmartHomeEcosystemCatalog.readyRoutes());
        assertEquals(4, SmartHomeEcosystemCatalog.totalRoutes());
    }

    @Test
    public void alexaAndGoogleUseHomeAssistantBridge() {
        assertTrue(SmartHomeEcosystemCatalog.usesHomeAssistantBridge(
                SmartHomeEcosystemCatalog.Ecosystem.AMAZON_ALEXA));
        assertTrue(SmartHomeEcosystemCatalog.usesHomeAssistantBridge(
                SmartHomeEcosystemCatalog.Ecosystem.GOOGLE_HOME));
        assertFalse(SmartHomeEcosystemCatalog.usesHomeAssistantBridge(
                SmartHomeEcosystemCatalog.Ecosystem.HOME_ASSISTANT));
    }

    @Test
    public void matterIsReservedButNotAdvertisedAsReady() {
        assertFalse(SmartHomeEcosystemCatalog.isReady(
                SmartHomeEcosystemCatalog.Ecosystem.MATTER));
    }

    @Test
    public void noAssistantMayBypassTheAuthorizedRelayPath() {
        for (SmartHomeEcosystemCatalog.Ecosystem ecosystem
                : SmartHomeEcosystemCatalog.Ecosystem.values()) {
            assertFalse(SmartHomeEcosystemCatalog.permitsDirectCloudRelay(ecosystem));
        }
    }
}
