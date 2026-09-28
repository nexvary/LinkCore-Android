package com.fgmachines.rck;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.Closeable;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Small authenticated HTTP API for local/VPN remote control and Home Assistant.
 * Intended for trusted LAN/VPN use. Internet exposure should terminate HTTPS
 * and authentication at a trusted reverse proxy/VPN.
 */
public final class LocalApiServer implements Closeable {
    public static final int PORT = 18086;
    private static final int MAX_LINE = 16 * 1024;

    private final ControllerHub hub;
    private final FleetStore fleet;
    private final HistoryStore history;
    private final AccessControlStore access;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private volatile ServerSocket serverSocket;

    public LocalApiServer(ControllerHub hub, FleetStore fleet,
                          HistoryStore history, AccessControlStore access) {
        this.hub = hub;
        this.fleet = fleet;
        this.history = history;
        this.access = access;
    }

    public synchronized void start() throws IOException {
        if (isRunning()) return;
        if (workers.isShutdown()) throw new IOException("Local API worker is shut down");
        if (serverSocket != null) {
            try { serverSocket.close(); } catch (IOException ignored) { }
            serverSocket = null;
        }
        ServerSocket socket = new ServerSocket(PORT);
        socket.setReuseAddress(true);
        serverSocket = socket;
        running.set(true);
        workers.execute(this::acceptLoop);
    }

    public boolean isRunning() {
        ServerSocket socket = serverSocket;
        return running.get() && socket != null && socket.isBound() && !socket.isClosed();
    }

    private void acceptLoop() {
        while (running.get()) {
            try {
                ServerSocket listener = serverSocket;
                if (listener == null || listener.isClosed()) break;
                Socket socket = listener.accept();
                socket.setSoTimeout(5000);
                workers.execute(() -> handle(socket));
            } catch (IOException error) {
                synchronized (this) {
                    if (running.get()) {
                        running.set(false);
                        try { if (serverSocket != null) serverSocket.close(); }
                        catch (IOException ignored) { }
                        serverSocket = null;
                    }
                }
                break;
            }
        }
    }

    private void handle(Socket socket) {
        if (!EndpointSecurity.isTrustedPeer(socket.getInetAddress())) {
            try { socket.close(); } catch (IOException ignored) { }
            return;
        }
        try (Socket closeable = socket;
             BufferedReader reader = new BufferedReader(new InputStreamReader(
                     closeable.getInputStream(), StandardCharsets.UTF_8));
             BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
                     closeable.getOutputStream(), StandardCharsets.UTF_8))) {

            String requestLine = reader.readLine();
            if (requestLine == null || requestLine.length() > MAX_LINE) return;
            String[] first = requestLine.split(" ");
            if (first.length < 2) {
                writeJson(writer, 400, error("bad_request"));
                return;
            }
            String method = first[0].toUpperCase();
            String rawTarget = first[1];

            Map<String, String> headers = new LinkedHashMap<>();
            String line;
            while ((line = reader.readLine()) != null && !line.isEmpty()) {
                if (line.length() > MAX_LINE) {
                    writeJson(writer, 431, error("headers_too_large"));
                    return;
                }
                int colon = line.indexOf(':');
                if (colon > 0) {
                    headers.put(line.substring(0, colon).trim().toLowerCase(),
                            line.substring(colon + 1).trim());
                }
            }

            String token = bearerToken(headers.get("authorization"));
            if (rawTarget.startsWith("/api/v1/health")) {
                JSONObject body = new JSONObject();
                body.put("ok", true);
                body.put("local_first", true);
                body.put("controller_port", ModelCatalog.CONTROLLER_PORT);
                body.put("api_port", PORT);
                writeJson(writer, 200, body);
                return;
            }

            AccessControlStore.Role required = "GET".equals(method)
                    ? AccessControlStore.Role.VIEW : AccessControlStore.Role.CONTROL;
            AccessControlStore.AccessEntry accessEntry = access.entryForToken(token);
            if (accessEntry == null || !accessEntry.role.allows(required)) {
                writeJson(writer, 401, error("unauthorized"));
                return;
            }

            ParsedTarget target = ParsedTarget.parse(rawTarget);
            route(writer, method, target, accessEntry);
        } catch (Exception ignored) {
            // Per-client failures must not terminate the controller service.
        }
    }

    private void route(BufferedWriter writer, String method, ParsedTarget target,
                       AccessControlStore.AccessEntry accessEntry)
            throws IOException, JSONException {
        String[] segments = target.path.split("/");
        if ("GET".equals(method) && "/api/v1/devices".equals(target.path)) {
            JSONArray devices = new JSONArray();
            for (FleetStore.DeviceRecord record : fleet.list()) {
                if (!accessEntry.allowsMac(record.mac)) continue;
                ControllerHub.DeviceState live = hub.state(record.mac);
                JSONObject item = new JSONObject();
                item.put("mac", record.mac);
                item.put("name", record.displayName());
                item.put("room", record.room);
                item.put("firmware", live != null ? live.firmwareVersion : record.firmware);
                item.put("connected", live != null && live.connected);
                item.put("last_seen", record.lastSeenAt);
                JSONArray outletNames = new JSONArray();
                for (int outlet = 1; outlet <= 4; outlet++) {
                    outletNames.put(fleet.outletName(record.mac, outlet));
                }
                item.put("outlet_names", outletNames);
                if (live != null) {
                    item.put("connected_since", live.connectedSince);
                    item.put("remote_address", live.remoteAddress);
                    if (live.telemetry != null) item.put("telemetry", telemetryJson(live.telemetry));
                }
                devices.put(item);
            }
            JSONObject body = new JSONObject();
            body.put("devices", devices);
            writeJson(writer, 200, body);
            return;
        }

        if (segments.length == 7
                && "POST".equals(method)
                && "api".equals(segments[1])
                && "v1".equals(segments[2])
                && "devices".equals(segments[3])
                && "outlets".equals(segments[5])) {
            String mac = FleetStore.normalizeMac(segments[4]);
            int outlet;
            try { outlet = Integer.parseInt(segments[6]); }
            catch (NumberFormatException error) { outlet = -1; }
            String state = target.query.get("state");
            if (outlet < 1 || outlet > 4 || (!"on".equals(state) && !"off".equals(state))) {
                writeJson(writer, 400, error("invalid_outlet_command"));
                return;
            }
            if (!accessEntry.allowsMac(mac)) {
                writeJson(writer, 403, error("device_not_shared"));
                return;
            }
            if (!hub.isConnected(mac)) {
                writeJson(writer, 409, error("device_offline"));
                return;
            }
            hub.setOutlet(mac, outlet, "on".equals(state));
            history.recordEvent(mac, outlet, "api_command", state, System.currentTimeMillis());
            JSONObject body = new JSONObject();
            body.put("ok", true);
            body.put("mac", mac);
            body.put("outlet", outlet);
            body.put("state", state);
            writeJson(writer, 200, body);
            return;
        }

        if (segments.length == 5
                && "GET".equals(method)
                && "api".equals(segments[1])
                && "v1".equals(segments[2])
                && "history".equals(segments[3])) {
            String mac = FleetStore.normalizeMac(segments[4]);
            if (!accessEntry.allowsMac(mac)) {
                writeJson(writer, 403, error("device_not_shared"));
                return;
            }
            int hours = 24;
            try { hours = Integer.parseInt(target.query.getOrDefault("hours", "24")); }
            catch (NumberFormatException ignored) { }
            hours = Math.max(1, Math.min(24 * 31, hours));
            long since = System.currentTimeMillis() - hours * 60L * 60L * 1000L;
            HistoryStore.Summary summary = history.summary(mac, since);
            JSONObject body = new JSONObject();
            body.put("mac", mac);
            body.put("hours", hours);
            body.put("energy_delta_kwh", summary.energyDeltaKWh);
            body.put("average_power_w", summary.averagePowerW);
            body.put("max_power_w", summary.maxPowerW);
            writeJson(writer, 200, body);
            return;
        }

        writeJson(writer, 404, error("not_found"));
    }

    private static JSONObject telemetryJson(MttlProtocol.Telemetry telemetry) throws JSONException {
        JSONObject result = new JSONObject();
        JSONArray outlets = new JSONArray();
        double totalPower = 0.0;
        double totalEnergy = 0.0;
        int maxTemp = Integer.MIN_VALUE;
        for (MttlProtocol.OutletTelemetry outlet : telemetry.outlets) {
            JSONObject item = new JSONObject();
            item.put("channel", outlet.channel);
            item.put("on", outlet.relayOn);
            item.put("power_w", outlet.powerW);
            item.put("energy_kwh", outlet.energyKWh);
            item.put("temperature_c", outlet.temperatureC);
            item.put("event_code", outlet.eventCode);
            outlets.put(item);
            totalPower += Math.max(0.0, outlet.powerW);
            totalEnergy += Math.max(0.0, outlet.energyKWh);
            maxTemp = Math.max(maxTemp, outlet.temperatureC);
        }
        result.put("outlets", outlets);
        result.put("total_power_w", totalPower);
        result.put("total_energy_kwh", totalEnergy);
        result.put("max_temperature_c", maxTemp == Integer.MIN_VALUE ? JSONObject.NULL : maxTemp);
        return result;
    }

    private static String bearerToken(String authorization) {
        if (authorization == null) return "";
        String prefix = "Bearer ";
        return authorization.regionMatches(true, 0, prefix, 0, prefix.length())
                ? authorization.substring(prefix.length()).trim() : "";
    }

    private static JSONObject error(String code) {
        JSONObject object = new JSONObject();
        try {
            object.put("ok", false);
            object.put("error", code);
        } catch (JSONException ignored) { }
        return object;
    }

    private static void writeJson(BufferedWriter writer, int status, JSONObject body) throws IOException {
        byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
        writer.write("HTTP/1.1 " + status + " " + statusText(status) + "\r\n");
        writer.write("Content-Type: application/json; charset=utf-8\r\n");
        writer.write("Content-Length: " + bytes.length + "\r\n");
        writer.write("Connection: close\r\n");
        writer.write("Cache-Control: no-store\r\n\r\n");
        writer.write(new String(bytes, StandardCharsets.UTF_8));
        writer.flush();
    }

    private static String statusText(int status) {
        switch (status) {
            case 200: return "OK";
            case 400: return "Bad Request";
            case 401: return "Unauthorized";
            case 403: return "Forbidden";
            case 404: return "Not Found";
            case 409: return "Conflict";
            case 431: return "Request Header Fields Too Large";
            default: return "Error";
        }
    }

    @Override public synchronized void close() {
        running.set(false);
        try { if (serverSocket != null) serverSocket.close(); }
        catch (IOException ignored) { }
        serverSocket = null;
        workers.shutdownNow();
    }

    static final class ParsedTarget {
        final String path;
        final Map<String, String> query;
        ParsedTarget(String path, Map<String, String> query) {
            this.path = path; this.query = query;
        }

        static ParsedTarget parse(String raw) {
            int q = raw.indexOf('?');
            String path = q >= 0 ? raw.substring(0, q) : raw;
            String rawQuery = q >= 0 ? raw.substring(q + 1) : "";
            Map<String, String> query = new LinkedHashMap<>();
            if (!rawQuery.isEmpty()) {
                for (String pair : rawQuery.split("&")) {
                    int equals = pair.indexOf('=');
                    String key = equals >= 0 ? pair.substring(0, equals) : pair;
                    String value = equals >= 0 ? pair.substring(equals + 1) : "";
                    query.put(decode(key), decode(value).toLowerCase());
                }
            }
            return new ParsedTarget(path, query);
        }

        private static String decode(String value) {
            try { return URLDecoder.decode(value, StandardCharsets.UTF_8.name()); }
            catch (Exception error) { return value; }
        }
    }
}
