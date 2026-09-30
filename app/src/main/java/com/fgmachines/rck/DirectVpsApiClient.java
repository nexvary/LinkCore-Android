package com.fgmachines.rck;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import javax.net.ssl.HttpsURLConnection;

/** Owner panel client. HTTPS only; credentials stay in memory, never in preferences. */
public final class DirectVpsApiClient implements AutoCloseable {
    public static final String DEFAULT_SERVER = "https://link.fgmachines.org";
    private final String origin;
    interface ConnectionFactory { HttpsURLConnection open(String url) throws IOException; }
    private final ConnectionFactory connections;
    private volatile String authorization;
    private volatile HttpsURLConnection active;

    public DirectVpsApiClient(String server, String username, String password) {
        this(server, username, password, url -> (HttpsURLConnection) URI.create(url).toURL().openConnection());
    }

    DirectVpsApiClient(String server, String username, String password, ConnectionFactory connections) {
        origin = normalizeServer(server);
        this.connections = connections;
        if (username == null || username.trim().isEmpty() || username.contains(":")
                || username.contains("\n") || username.contains("\r")
                || password == null || password.isEmpty()) {
            throw new IllegalArgumentException("credentials");
        }
        authorization = "Basic " + Base64.getEncoder().encodeToString(
                (username.trim() + ":" + password).getBytes(StandardCharsets.UTF_8));
    }

    static String normalizeServer(String server) {
        try {
            URI uri = new URI(server == null ? "" : server.trim());
            String path = uri.getPath();
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                    || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                    || uri.getRawFragment() != null || uri.getPort() == 0 || uri.getPort() > 65535
                    || !(path == null || path.isEmpty() || path.equals("/")
                    || path.equals("/panel") || path.equals("/panel/"))) {
                throw new IllegalArgumentException("https");
            }
            return new URI("https", null, uri.getHost(), uri.getPort(), null, null, null).toString();
        } catch (URISyntaxException e) {
            throw new IllegalArgumentException("https");
        }
    }

    public List<Device> devices() throws IOException, JSONException {
        return parseDevices(request("GET", "/panel/api/direct/devices"));
    }

    public String setOutlet(String mac, int outlet, boolean on) throws IOException, JSONException {
        JSONObject result = request("POST", commandPath(mac, outlet, on));
        if (!"direct-vps".equals(result.optString("source"))) throw new IOException("protocol");
        String status = result.optString("status");
        if (!status.equals("confirmed") && !status.equals("failed") && !status.equals("timeout")) {
            throw new IOException("protocol");
        }
        return status;
    }

    static String commandPath(String mac, int outlet, boolean on) {
        if (mac == null || !mac.matches("[0-9a-fA-F]{12}") || outlet < 1 || outlet > 4) {
            throw new IllegalArgumentException("outlet");
        }
        return "/panel/api/direct/devices/" + mac.toUpperCase(Locale.ROOT)
                + "/outlets/" + outlet + "?state=" + (on ? "on" : "off");
    }

    private JSONObject request(String method, String path) throws IOException, JSONException {
        String auth = authorization;
        if (auth == null) throw new IOException("closed");
        HttpsURLConnection connection = connections.open(origin + path);
        active = connection;
        try {
            connection.setInstanceFollowRedirects(false); // Never forward credentials on redirects.
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(method.equals("POST") ? 20000 : 7000);
            connection.setRequestMethod(method);
            connection.setRequestProperty("Authorization", auth);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Cache-Control", "no-store");
            connection.setUseCaches(false);
            if (method.equals("POST")) {
                connection.setDoOutput(true);
                connection.setFixedLengthStreamingMode(0);
                connection.getOutputStream().close();
            }
            int code = connection.getResponseCode();
            if (code != 200) throw new ApiException(code);
            String type = connection.getContentType();
            if (type == null || !type.toLowerCase(Locale.ROOT).contains("application/json")) {
                throw new IOException("protocol");
            }
            try (InputStream in = connection.getInputStream();
                 ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096];
                int count;
                while ((count = in.read(buffer)) != -1) {
                    if (out.size() + count > 262144) throw new IOException("response-size");
                    out.write(buffer, 0, count);
                }
                return new JSONObject(out.toString(StandardCharsets.UTF_8.name()));
            }
        } finally {
            connection.disconnect();
            active = null;
        }
    }

    static List<Device> parseDevices(JSONObject response) throws JSONException {
        if (!"direct-vps".equals(response.optString("source"))) throw new JSONException("source");
        JSONArray array = response.getJSONArray("devices");
        List<Device> devices = new ArrayList<>();
        for (int i = 0; i < array.length(); i++) {
            JSONObject raw = array.getJSONObject(i);
            String mac = raw.getString("mac").toUpperCase(Locale.ROOT);
            if (!mac.matches("[0-9A-F]{12}")) throw new JSONException("mac");
            devices.add(new Device(mac, raw));
        }
        return devices;
    }

    public static final class Device {
        public final String mac;
        public final JSONObject data;
        Device(String mac, JSONObject data) { this.mac = mac; this.data = data; }
        public boolean online() { return data.optBoolean("connected", false); }
        public JSONObject outlet(int channel) {
            JSONArray rows = data.optJSONArray("outlets");
            if (rows != null) for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row != null && row.optInt("channel") == channel) return row;
            }
            return new JSONObject();
        }
        public String state(int channel) {
            String relay = outlet(channel).optString("relay");
            return relay.equals("on") || relay.equals("off") ? relay : "unknown";
        }
        public boolean canControl(int channel) {
            if (!online() || !data.optBoolean("control_enabled") || state(channel).equals("unknown")) return false;
            JSONArray inFlight = data.optJSONArray("pending_outlets");
            if (inFlight != null && inFlight.length() > 0) return false; // Service allows one command per device.
            JSONArray allowed = data.optJSONArray("allowed_outlets");
            if (allowed != null) for (int i = 0; i < allowed.length(); i++) {
                if (allowed.optInt(i) == channel) return !pending(channel);
            }
            return false;
        }
        public boolean pending(int channel) {
            JSONArray pending = data.optJSONArray("pending_outlets");
            if (pending != null) for (int i = 0; i < pending.length(); i++) {
                if (pending.optInt(i) == channel) return true;
            }
            return false;
        }
    }

    public static final class ApiException extends IOException {
        public final int status;
        ApiException(int status) { super("HTTP " + status); this.status = status; }
    }

    @Override public void close() {
        authorization = null;
        HttpsURLConnection connection = active;
        if (connection != null) connection.disconnect();
    }
}
