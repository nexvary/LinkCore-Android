package com.fgmachines.rck;

import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;

/**
 * Public rollout gates for the optional FG Link VPS path.
 *
 * Local/LAN/ZeroTier control remains the default and must keep working even when
 * the VPS path is disabled or unavailable. Direct VPS provisioning is available; self-service signup stays disabled.
 * Existing users keep explicit local and Direct VPS routes.
 */
public final class VpsFeatureFlags {
    public static final boolean PUBLIC_VPS_DIRECT_ENABLED = true;
    public static final boolean SELF_SERVICE_ACCOUNT_ENABLED = false;

    public static final String VPS_HOST = "link.fgmachines.org";

    private VpsFeatureFlags() { }

    /**
     * Resolve the VPS hostname to an IPv4 address before joining the strip setup AP.
     * MTTL provisioning accepts a controller IPv4 value, not an HTTPS URL.
     */
    public static String resolveDirectControllerIpv4() throws IOException {
        final InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(VPS_HOST);
        } catch (Exception error) {
            throw new IOException("Could not resolve FG Link VPS IPv4", error);
        }

        for (InetAddress address : addresses) {
            if (address instanceof Inet4Address
                    && !address.isAnyLocalAddress()
                    && !address.isLoopbackAddress()
                    && !address.isLinkLocalAddress()) {
                return address.getHostAddress();
            }
        }
        throw new IOException("FG Link VPS has no usable IPv4 address");
    }
}
