package com.fgmachines.rck;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Optional client for another FG Machines RCK controller exposed through a
 * trusted HTTPS endpoint or private VPN. Local control remains the default.
 */
public final class RemoteApiClient {
    private final String baseUrl;
    private final String token;
    private final DeviceBoundSigner signer;
    private final String controllerId;

    public RemoteApiClient(String baseUrl, String token) {
        this(baseUrl, token, null, "");
    }

    public RemoteApiClient(
            String baseUrl,
            String token,
            DeviceBoundSigner signer,
            String controllerId) {
        String normalized = baseUrl == null ? "" : baseUrl.trim();
        while (normalized.endsWith("/")) normalized = normalized.substring(0, normalized.length() - 1);
        this.baseUrl = normalized;
        this.token = token == null ? "" : token.trim();
        this.signer = signer;
        this.controllerId = controllerId == null ? "" : controllerId.trim();
    }

    public List<RemoteDevice> listDevices() throws IOException {
        JSONObject response = request("GET", "/api/v1/devices");
        JSONArray devices = response.optJSONArray("devices");
        List<RemoteDevice> out = new ArrayList<>();
        if (devices == null) return out;
        for (int i = 0; i < devices.length(); i++) {
            JSONObject item = devices.optJSONObject(i);
            if (item == null) continue;
            out.add(new RemoteDevice(
                    item.optString("mac"),
                    item.optString("name"),
                    item.optString("room"),
                    item.optBoolean("connected"),
                    item.optLong("last_seen")
            ));
        }
        return out;
    }

    public void setOutlet(String mac, int outlet, boolean on) throws IOException {
        if (outlet < 1 || outlet > 4) throw new IOException("Outlet must be 1..4");
        String safeMac = FleetStore.normalizeMac(mac);
        String state = on ? "on" : "off";

        // LAN / ZeroTier is deliberately independent from FG Cloud. Private/VPN
        // endpoints use the local API token and do not need cloud provisioning.
        if (signer == null || controllerId.isEmpty()) {
            if (!EndpointSecurity.isPrivateOrVpnEndpoint(baseUrl)) {
                throw new IOException(
                        "Public remote control requires the device-bound FG Cloud identity");
            }
            request("POST", "/api/v1/devices/" + safeMac + "/outlets/" + outlet
                    + "?state=" + state);
            return;
        }

        long issuedAt = System.currentTimeMillis() / 1000L;
        long validUntil = issuedAt + 90L;
        String nonce = DeviceBoundSigner.newNonce();
        try {
            String keyId = signer.keyId();
            String canonical = DeviceBoundSigner.canonical(
                    controllerId, safeMac, outlet, state, issuedAt, validUntil, nonce, keyId);
            String signature = signer.sign(canonical);
            Map<String, String> headers = new LinkedHashMap<>();
            headers.put("X-FG-Key-Id", keyId);
            headers.put("X-FG-Nonce", nonce);
            headers.put("X-FG-Issued-At", String.valueOf(issuedAt));
            headers.put("X-FG-Valid-Until", String.valueOf(validUntil));
            headers.put("X-FG-Signature", signature);
            request("POST", "/api/v1/devices/" + safeMac + "/outlets/" + outlet
                    + "?state=" + state, headers);
        } catch (IOException error) {
            throw error;
        } catch (Exception error) {
            throw new IOException("Unable to sign remote command with Android Keystore", error);
        }
    }

    public JSONObject history(String mac, int hours) throws IOException {
        return request("GET", "/api/v1/history/" + FleetStore.normalizeMac(mac)
                + "?hours=" + Math.max(1, hours));
    }

    public JSONObject health() throws IOException {
        return request("GET", "/api/v1/health");
    }

    private JSONObject request(String method, String path) throws IOException {
        return request(method, path, java.util.Collections.emptyMap());
    }

    private JSONObject request(String method, String path, Map<String, String> extraHeaders)
            throws IOException {
        EndpointSecurity.validateRemoteEndpoint(baseUrl);
        URL url = new URL(baseUrl + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(7000);
        connection.setRequestProperty("Accept", "application/json");
        if (!token.isEmpty()) connection.setRequestProperty("Authorization", "Bearer " + token);
        if (extraHeaders != null) {
            for (Map.Entry<String, String> header : extraHeaders.entrySet()) {
                if (header.getKey() != null && header.getValue() != null) {
                    connection.setRequestProperty(header.getKey(), header.getValue());
                }
            }
        }
        connection.setDoInput(true);
        if ("POST".equals(method)) {
            connection.setDoOutput(true);
            connection.getOutputStream().write(new byte[0]);
        }
        int code = connection.getResponseCode();
        java.io.InputStream stream = code >= 200 && code < 300
                ? connection.getInputStream() : connection.getErrorStream();
        StringBuilder body = new StringBuilder();
        if (stream != null) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) body.append(line);
            }
        }
        connection.disconnect();
        if (code < 200 || code >= 300) {
            throw new IOException("Remote API HTTP " + code + ": " + body);
        }
        try {
            return new JSONObject(body.toString());
        } catch (Exception error) {
            throw new IOException("Remote API returned invalid JSON", error);
        }
    }

    public static final class RemoteDevice {
        public final String mac;
        public final String name;
        public final String room;
        public final boolean connected;
        public final long lastSeen;

        RemoteDevice(String mac, String name, String room, boolean connected, long lastSeen) {
            this.mac = mac;
            this.name = name;
            this.room = room;
            this.connected = connected;
            this.lastSeen = lastSeen;
        }

        @Override public String toString() {
            String label = name == null || name.isEmpty() ? mac : name;
            if (room != null && !room.isEmpty()) label += " · " + room;
            return label + (connected ? " · ONLINE" : " · OFFLINE");
        }
    }
}
