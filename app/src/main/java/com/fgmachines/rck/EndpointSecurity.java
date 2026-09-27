package com.fgmachines.rck;

import java.io.IOException;
import java.net.InetAddress;
import java.net.URL;

/** Network boundary checks shared by the local API and remote-control client. */
final class EndpointSecurity {
    private EndpointSecurity() { }

    static boolean isTrustedPeer(InetAddress address) {
        if (address == null) return false;
        if (address.isLoopbackAddress() || address.isSiteLocalAddress()
                || address.isLinkLocalAddress()) return true;

        byte[] raw = address.getAddress();
        if (raw.length == 4) {
            int first = raw[0] & 0xFF;
            int second = raw[1] & 0xFF;
            // CGNAT/private overlay range commonly used by VPNs such as Tailscale.
            return first == 100 && second >= 64 && second <= 127;
        }
        if (raw.length == 16) {
            int first = raw[0] & 0xFF;
            // IPv6 unique-local addresses fc00::/7.
            return (first & 0xFE) == 0xFC;
        }
        return false;
    }

    static boolean isPrivateOrVpnEndpoint(String baseUrl) throws IOException {
        if (baseUrl == null || baseUrl.trim().isEmpty()) return false;
        final URL url;
        try {
            url = new URL(baseUrl.trim());
        } catch (Exception error) {
            throw new IOException("Remote endpoint is not a valid URL", error);
        }
        String host = url.getHost();
        if (host == null || host.trim().isEmpty()) return false;
        InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(host);
        } catch (Exception error) {
            throw new IOException("Could not resolve remote endpoint host", error);
        }
        if (addresses.length == 0) return false;
        for (InetAddress address : addresses) {
            if (!isTrustedPeer(address)) return false;
        }
        return true;
    }

    static void validateRemoteEndpoint(String baseUrl) throws IOException {
        if (baseUrl == null || baseUrl.trim().isEmpty()) {
            throw new IOException("Remote endpoint is empty");
        }
        final URL url;
        try {
            url = new URL(baseUrl.trim());
        } catch (Exception error) {
            throw new IOException("Remote endpoint is not a valid URL", error);
        }
        String protocol = url.getProtocol();
        if (!"http".equalsIgnoreCase(protocol) && !"https".equalsIgnoreCase(protocol)) {
            throw new IOException("Remote endpoint must use HTTP or HTTPS");
        }
        if (url.getUserInfo() != null) {
            throw new IOException("Credentials in the endpoint URL are not allowed");
        }
        if ("https".equalsIgnoreCase(protocol)) return;

        String host = url.getHost();
        if (host == null || host.trim().isEmpty()) {
            throw new IOException("Remote endpoint host is missing");
        }
        InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(host);
        } catch (Exception error) {
            throw new IOException("Could not resolve remote endpoint host", error);
        }
        if (addresses.length == 0) throw new IOException("Remote endpoint host has no address");
        for (InetAddress address : addresses) {
            if (!isTrustedPeer(address)) {
                throw new IOException("Plain HTTP is allowed only for local/private VPN addresses; use HTTPS for public endpoints");
            }
        }
    }
}
