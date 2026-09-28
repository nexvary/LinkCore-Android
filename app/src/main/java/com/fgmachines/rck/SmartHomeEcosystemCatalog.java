package com.fgmachines.rck;

/** Product-level routing policy for external smart-home ecosystems. */
final class SmartHomeEcosystemCatalog {
    enum Ecosystem {
        HOME_ASSISTANT,
        AMAZON_ALEXA,
        GOOGLE_HOME,
        MATTER
    }

    private SmartHomeEcosystemCatalog() { }

    static int totalRoutes() {
        return Ecosystem.values().length;
    }

    static int readyRoutes() {
        int count = 0;
        for (Ecosystem ecosystem : Ecosystem.values()) {
            if (isReady(ecosystem)) count++;
        }
        return count;
    }

    static boolean isReady(Ecosystem ecosystem) {
        return ecosystem == Ecosystem.HOME_ASSISTANT
                || ecosystem == Ecosystem.AMAZON_ALEXA
                || ecosystem == Ecosystem.GOOGLE_HOME;
    }

    static boolean usesHomeAssistantBridge(Ecosystem ecosystem) {
        return ecosystem == Ecosystem.AMAZON_ALEXA
                || ecosystem == Ecosystem.GOOGLE_HOME;
    }

    static boolean isBeta(Ecosystem ecosystem) {
        return ecosystem == Ecosystem.MATTER;
    }

    static boolean permitsDirectCloudRelay(Ecosystem ecosystem) {
        return false;
    }
}
