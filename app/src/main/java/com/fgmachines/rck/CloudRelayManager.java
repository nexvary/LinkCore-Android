package com.fgmachines.rck;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.Closeable;
import java.io.IOException;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Optional outbound-only bridge between the local MTTL controller and the VPS.
 * It never exposes TCP 10086 or HTTP 18086 to the public Internet.
 */
public final class CloudRelayManager implements Closeable {
    public static final String PREF_CLOUD_SYNC_ENABLED = "cloud_sync_enabled";
    public static final String PREF_CLOUD_CONTROLLER_ID = "cloud_controller_id";
    public static final String PREF_CLOUD_CONTROLLER_KEY = "cloud_controller_key";
    public static final String PREF_CLOUD_REGISTERED_MACS = "cloud_registered_macs";
    public static final String PREF_CLOUD_BINDING_KEY_ID = "cloud_binding_key_id";
    private static final String PREF_CLOUD_SEEN_NONCES = "cloud_seen_command_nonces";
    private static final int MAX_SEEN_NONCES = 512;
    private static final String PREFS = "fg_rck_settings";
    private static final String PREF_REMOTE_ENDPOINT = "remote_endpoint";
    private static final String PREF_REMOTE_TOKEN = "remote_token";

    private final Context context;
    private final SharedPreferences prefs;
    private final ControllerHub hub;
    private final FleetStore fleetStore;
    private final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor();
    private final Set<String> registeredMacs = new HashSet<>();
    private volatile boolean started;

    public CloudRelayManager(Context context, ControllerHub hub, FleetStore fleetStore) {
        this.context = context.getApplicationContext();
        this.prefs = this.context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        this.hub = hub;
        this.fleetStore = fleetStore;
        this.registeredMacs.addAll(
                prefs.getStringSet(PREF_CLOUD_REGISTERED_MACS, java.util.Collections.emptySet()));
    }

    public synchronized void start() {
        if (started) return;
        started = true;
        worker.scheduleWithFixedDelay(this::safeSync, 3, 15, TimeUnit.SECONDS);
    }

    private void safeSync() {
        try {
            syncOnce();
        } catch (Exception ignored) {
            // Local control must remain available even when the VPS is offline or misconfigured.
        }
    }

    void syncOnce() throws IOException {
        if (!prefs.getBoolean(PREF_CLOUD_SYNC_ENABLED, false)) return;
        String endpoint = prefs.getString(PREF_REMOTE_ENDPOINT, "");
        String bearer = prefs.getString(PREF_REMOTE_TOKEN, "");
        if (endpoint == null || endpoint.trim().isEmpty()
                || bearer == null || bearer.trim().isEmpty()) return;

        CloudApiClient api = new CloudApiClient(endpoint);
        String controllerId = prefs.getString(PREF_CLOUD_CONTROLLER_ID, "");
        String controllerKey = prefs.getString(PREF_CLOUD_CONTROLLER_KEY, "");
        if (controllerId == null) controllerId = "";
        if (controllerKey == null) controllerKey = "";

        if (controllerId.isEmpty() || controllerKey.isEmpty()) {
            CloudApiClient.ControllerCredentials created = api.createController(
                    bearer, "Android " + Build.MODEL);
            if (created.controllerId.isEmpty() || created.controllerKey.isEmpty()) {
                throw new IOException("Cloud controller registration returned empty credentials");
            }
            controllerId = created.controllerId;
            controllerKey = created.controllerKey;
            prefs.edit()
                    .putString(PREF_CLOUD_CONTROLLER_ID, controllerId)
                    .putString(PREF_CLOUD_CONTROLLER_KEY, controllerKey)
                    .apply();
            registeredMacs.clear();
            prefs.edit()
                    .remove(PREF_CLOUD_REGISTERED_MACS)
                    .remove(PREF_CLOUD_BINDING_KEY_ID)
                    .remove(PREF_CLOUD_SEEN_NONCES)
                    .apply();
        }

        DeviceBoundSigner signer;
        try {
            signer = new DeviceBoundSigner(context);
            String keyId = signer.keyId();
            String boundKeyId = prefs.getString(PREF_CLOUD_BINDING_KEY_ID, "");
            if (!keyId.equalsIgnoreCase(boundKeyId == null ? "" : boundKeyId)) {
                api.bindDeviceInstallation(
                        bearer,
                        controllerId,
                        signer,
                        "Android " + Build.MODEL);
                prefs.edit().putString(PREF_CLOUD_BINDING_KEY_ID, keyId).apply();
            }
        } catch (Exception error) {
            throw new IOException("Device-bound cloud identity is unavailable", error);
        }

        List<FleetStore.DeviceRecord> devices = fleetStore.list();
        for (FleetStore.DeviceRecord device : devices) {
            if (!registeredMacs.contains(device.mac)) {
                api.registerDevice(bearer, controllerId, device);
                registeredMacs.add(device.mac);
                prefs.edit().putStringSet(
                        PREF_CLOUD_REGISTERED_MACS, new HashSet<>(registeredMacs)).apply();
            }
        }

        JSONArray heartbeatDevices = new JSONArray();
        for (FleetStore.DeviceRecord device : devices) {
            ControllerHub.DeviceState state = hub.state(device.mac);
            JSONObject item = CloudApiClient.json(
                    "mac", device.mac,
                    "connected", state != null && state.connected,
                    "firmware", state != null && state.firmwareVersion != null
                            ? state.firmwareVersion : device.firmware);
            heartbeatDevices.put(item);
        }
        api.heartbeat(controllerId, controllerKey, heartbeatDevices);

        JSONArray telemetryItems = new JSONArray();
        for (ControllerHub.DeviceState state : hub.connectedStates()) {
            if (state.telemetry == null) continue;
            telemetryItems.put(toTelemetryJson(state.mac, state.telemetry));
        }
        api.telemetry(controllerId, controllerKey, telemetryItems);

        JSONArray commands = api.pollCommands(controllerId, controllerKey);
        for (int i = 0; i < commands.length(); i++) {
            JSONObject command = commands.optJSONObject(i);
            if (command == null) continue;
            handleCommand(api, controllerId, controllerKey, command);
        }
    }

    private void handleCommand(CloudApiClient api, String controllerId, String controllerKey,
                               JSONObject command) {
        String commandId = command.optString("command_id");
        String mac = FleetStore.normalizeMac(command.optString("mac"));
        int outlet = command.optInt("outlet", 0);
        String state = command.optString("state", "").toLowerCase(java.util.Locale.ROOT);
        boolean on = "on".equals(state);
        if (commandId.isEmpty()) return;

        String status = "acked";
        String detail = "Verified device-bound command sent to MTTL locally";
        try {
            if (mac.isEmpty() || outlet < 1 || outlet > 4 || (!"on".equals(state) && !"off".equals(state))) {
                throw new IOException("invalid_command");
            }
            if (!registeredMacs.contains(mac)) {
                throw new IOException("device_not_owned_by_controller");
            }

            JSONObject proof = command.optJSONObject("proof");
            if (proof == null) throw new IOException("missing_device_bound_signature");

            String keyId = proof.optString("key_id", "").toLowerCase(java.util.Locale.ROOT);
            String nonce = proof.optString("nonce", "");
            long issuedAt = proof.optLong("issued_at", 0L);
            long validUntil = proof.optLong("valid_until", 0L);
            String signature = proof.optString("signature", "");
            long now = System.currentTimeMillis() / 1000L;

            DeviceBoundSigner signer = new DeviceBoundSigner(context);
            if (!signer.keyId().equalsIgnoreCase(keyId)) {
                throw new IOException("untrusted_installation_key");
            }
            if (issuedAt <= 0L || validUntil <= 0L || validUntil <= now
                    || issuedAt > now + 90L || issuedAt < now - 180L
                    || validUntil - issuedAt > 120L) {
                throw new IOException("expired_or_invalid_signed_window");
            }
            if (nonce.length() < 20 || wasNonceSeen(nonce)) {
                throw new IOException("replayed_command_nonce");
            }

            String canonical = DeviceBoundSigner.canonical(
                    controllerId, mac, outlet, state, issuedAt, validUntil, nonce, keyId);
            if (!signer.verifyOwn(canonical, signature)) {
                throw new IOException("invalid_device_bound_signature");
            }

            rememberNonce(nonce);
            if (!hub.isConnected(mac)) {
                throw new IOException("device_offline");
            }
            hub.setOutlet(mac, outlet, on);
            try { hub.refresh(mac); } catch (IOException ignored) { }
        } catch (Exception error) {
            status = "failed";
            detail = safe(error);
        }

        try {
            api.ack(controllerId, controllerKey, commandId, status, detail);
        } catch (IOException ignored) { }
    }

    private synchronized boolean wasNonceSeen(String nonce) {
        Set<String> values = prefs.getStringSet(
                PREF_CLOUD_SEEN_NONCES, java.util.Collections.emptySet());
        return values.contains(nonce);
    }

    private synchronized void rememberNonce(String nonce) {
        Set<String> current = prefs.getStringSet(
                PREF_CLOUD_SEEN_NONCES, java.util.Collections.emptySet());
        java.util.LinkedHashSet<String> copy = new java.util.LinkedHashSet<>(current);
        if (copy.size() >= MAX_SEEN_NONCES) {
            copy.clear();
        }
        copy.add(nonce);
        prefs.edit().putStringSet(PREF_CLOUD_SEEN_NONCES, copy).apply();
    }

    static JSONObject toTelemetryJson(String mac, MttlProtocol.Telemetry telemetry) throws IOException {
        double power = 0.0;
        double energy = 0.0;
        int maxTemp = 0;
        int relayMask = 0;
        String eventCode = "00";
        for (MttlProtocol.OutletTelemetry outlet : telemetry.outlets) {
            power += Math.max(0.0, outlet.powerW);
            energy += Math.max(0.0, outlet.energyKWh);
            maxTemp = Math.max(maxTemp, outlet.temperatureC);
            if (outlet.relayOn && outlet.channel >= 1 && outlet.channel <= 4) {
                relayMask |= 1 << (outlet.channel - 1);
            }
            if (outlet.eventCode != null && !"00".equals(outlet.eventCode)) {
                eventCode = outlet.eventCode;
            }
        }
        return CloudApiClient.json(
                "mac", FleetStore.normalizeMac(mac),
                "power_w", power,
                "energy_kwh", energy,
                "max_temp_c", maxTemp,
                "relay_mask", relayMask,
                "event_code", eventCode);
    }

    private static String safe(Throwable error) {
        if (error == null) return "unknown";
        String value = error.getMessage();
        return value == null || value.trim().isEmpty()
                ? error.getClass().getSimpleName() : value;
    }

    @Override public synchronized void close() {
        started = false;
        worker.shutdownNow();
    }
}
