package com.fgmachines.rck;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** HTTPS client for the optional FG Machines RCK cloud/VPS backend. */
public final class CloudApiClient {
    private final String baseUrl;

    public CloudApiClient(String baseUrl) {
        String normalized = baseUrl == null ? "" : baseUrl.trim();
        while (normalized.endsWith("/")) normalized = normalized.substring(0, normalized.length() - 1);
        this.baseUrl = normalized;
    }

    public AuthSession register(String email, String password) throws IOException {
        return auth("/api/v1/auth/register", email, password);
    }

    public AuthSession login(String email, String password) throws IOException {
        return auth("/api/v1/auth/login", email, password);
    }

    private AuthSession auth(String path, String email, String password) throws IOException {
        JSONObject body = json(
                "email", email == null ? "" : email.trim(),
                "password", password == null ? "" : password);
        JSONObject response = request("POST", path, "", "", body);
        return new AuthSession(response.optString("access_token"), response.optString("user_id"));
    }

    public ControllerCredentials createController(String bearer, String name) throws IOException {
        JSONObject body = json(
                "name", name == null || name.trim().isEmpty() ? "FG Machines RCK Android" : name.trim());
        JSONObject response = request("POST", "/api/v1/controllers", bearer, "", body);
        return new ControllerCredentials(
                response.optString("controller_id"),
                response.optString("controller_key"));
    }

    public void bindDeviceInstallation(
            String bearer,
            String controllerId,
            DeviceBoundSigner signer,
            String label) throws IOException {
        try {
            JSONObject body = json(
                    "key_id", signer.keyId(),
                    "public_key_b64", signer.publicKeyBase64(),
                    "label", label == null ? "" : label,
                    "hardware_backed", signer.isHardwareBacked());
            request("PUT", "/api/v1/controllers/" + controllerId + "/device-binding",
                    bearer, "", body);
        } catch (IOException error) {
            throw error;
        } catch (Exception error) {
            throw new IOException("Unable to register device-bound signing identity", error);
        }
    }

    public void registerDevice(String bearer, String controllerId, FleetStore.DeviceRecord device)
            throws IOException {
        JSONObject body = json(
                "controller_id", controllerId,
                "mac", device.mac,
                "name", device.name,
                "room", device.room,
                "firmware", device.firmware);
        request("POST", "/api/v1/devices", bearer, "", body);
    }

    public void heartbeat(String controllerId, String controllerKey, JSONArray devices)
            throws IOException {
        JSONObject body = json("devices", devices == null ? new JSONArray() : devices);
        request("POST", "/api/v1/controllers/" + controllerId + "/heartbeat",
                "", controllerKey, body);
    }

    public void telemetry(String controllerId, String controllerKey, JSONArray items)
            throws IOException {
        if (items == null || items.length() == 0) return;
        JSONObject body = json("items", items);
        request("POST", "/api/v1/controllers/" + controllerId + "/telemetry",
                "", controllerKey, body);
    }

    public JSONArray pollCommands(String controllerId, String controllerKey) throws IOException {
        JSONObject response = request("GET",
                "/api/v1/controllers/" + controllerId + "/commands/poll?limit=20",
                "", controllerKey, null);
        JSONArray commands = response.optJSONArray("commands");
        return commands == null ? new JSONArray() : commands;
    }

    public void sendAlertEmail(String bearer, String subject, String message) throws IOException {
        JSONObject body = json(
                "subject", subject == null ? "" : subject.trim(),
                "body", message == null ? "" : message.trim());
        request("POST", "/api/v1/alerts/email", bearer, "", body);
    }

    public void ack(String controllerId, String controllerKey, String commandId,
                    String status, String detail) throws IOException {
        JSONObject body = json(
                "status", status,
                "detail", detail == null ? "" : detail);
        request("POST", "/api/v1/controllers/" + controllerId + "/commands/" + commandId + "/ack",
                "", controllerKey, body);
    }

    static JSONObject json(Object... pairs) throws IOException {
        if (pairs == null || pairs.length % 2 != 0) {
            throw new IOException("Invalid JSON field list");
        }
        JSONObject object = new JSONObject();
        try {
            for (int i = 0; i < pairs.length; i += 2) {
                object.put(String.valueOf(pairs[i]), pairs[i + 1]);
            }
            return object;
        } catch (Exception error) {
            throw new IOException("Unable to build JSON request", error);
        }
    }

    private JSONObject request(String method, String path, String bearer,
                               String controllerKey, JSONObject body) throws IOException {
        EndpointSecurity.validateRemoteEndpoint(baseUrl);
        HttpURLConnection connection = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(6000);
        connection.setReadTimeout(9000);
        connection.setRequestProperty("Accept", "application/json");
        if (bearer != null && !bearer.isEmpty()) {
            connection.setRequestProperty("Authorization", "Bearer " + bearer);
        }
        if (controllerKey != null && !controllerKey.isEmpty()) {
            connection.setRequestProperty("X-Controller-Key", controllerKey);
        }
        if (body != null) {
            byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(payload.length);
            connection.getOutputStream().write(payload);
        }
        int code = connection.getResponseCode();
        InputStream stream = code >= 200 && code < 300
                ? connection.getInputStream() : connection.getErrorStream();
        StringBuilder text = new StringBuilder();
        if (stream != null) {
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) text.append(line);
            }
        }
        connection.disconnect();
        if (code < 200 || code >= 300) {
            throw new IOException("Cloud API HTTP " + code + ": " + text);
        }
        if (text.length() == 0) return new JSONObject();
        try {
            return new JSONObject(text.toString());
        } catch (Exception error) {
            throw new IOException("Cloud API returned invalid JSON", error);
        }
    }

    public static final class AuthSession {
        public final String accessToken;
        public final String userId;
        AuthSession(String accessToken, String userId) {
            this.accessToken = accessToken == null ? "" : accessToken;
            this.userId = userId == null ? "" : userId;
        }
    }

    public static final class ControllerCredentials {
        public final String controllerId;
        public final String controllerKey;
        ControllerCredentials(String controllerId, String controllerKey) {
            this.controllerId = controllerId == null ? "" : controllerId;
            this.controllerKey = controllerKey == null ? "" : controllerKey;
        }
    }
}
