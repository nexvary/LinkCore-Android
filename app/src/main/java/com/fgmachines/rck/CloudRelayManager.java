package com.fgmachines.rck;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.Closeable;
import java.io.IOException;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Optional outbound-only bridge between the local FG Link controller and the VPS.
 *
 * Security boundary:
 * - the VPS receives only a hashed device fingerprint and privacy-reduced strip status;
 * - strip control uses random opaque references rather than raw MAC addresses;
 * - Wi-Fi credentials, ZeroTier secrets and local MTTL control material never leave the phone;
 * - no public inbound port is opened on Android.
 */
public final class CloudRelayManager implements Closeable {
    public static final boolean CLOUD_ON_HOLD = false;

    public static final String PREF_CLOUD_SYNC_ENABLED = "cloud_sync_enabled";
    public static final String PREF_CLOUD_LAST_STATUS = "cloud_last_status";
    public static final String PREF_CLOUD_LAST_SYNC_AT = "cloud_last_sync_at";
    public static final String PREF_VPS_API_TOKEN = "vps_api_token";
    public static final String FIXED_VPS_ENDPOINT = "https://link.fgmachines.org";

    // Legacy keys are kept for migration compatibility with older builds.
    public static final String PREF_CLOUD_CONTROLLER_ID = "cloud_controller_id";
    public static final String PREF_CLOUD_CONTROLLER_KEY = "cloud_controller_key";
    public static final String PREF_CLOUD_REGISTERED_MACS = "cloud_registered_macs";
    public static final String PREF_CLOUD_BINDING_KEY_ID = "cloud_binding_key_id";

    private static final String PREFS = "fg_rck_settings";

    private final Context context;
    private final SharedPreferences prefs;
    private final ControllerHub hub;
    private final FleetStore fleetStore;
    private final OutletRuntimeStore runtimeStore;
    private final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor();

    private volatile boolean started;
    private String boundConfiguration = "";

    public CloudRelayManager(Context context, ControllerHub hub, FleetStore fleetStore) {
        this.context = context.getApplicationContext();
        this.prefs = this.context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        this.hub = hub;
        this.fleetStore = fleetStore;
        this.runtimeStore = new OutletRuntimeStore(this.context);
    }

    public synchronized void start() {
        if (started) return;
        started = true;
        worker.scheduleWithFixedDelay(this::safeSync, 2, 5, TimeUnit.SECONDS);
    }

    private void safeSync() {
        try {
            syncOnce();
        } catch (Exception error) {
            String message = error.getMessage();
            if (message == null || message.trim().isEmpty()) {
                message = error.getClass().getSimpleName();
            }
            if (message.length() > 180) message = message.substring(0, 180);
            prefs.edit().putString(PREF_CLOUD_LAST_STATUS, "error:" + message).apply();
        }
    }

    void syncOnce() throws IOException {
        if (!prefs.getBoolean(PREF_CLOUD_SYNC_ENABLED, false)) return;

        String token = clean(prefs.getString(PREF_VPS_API_TOKEN, ""));
        if (token.isEmpty()) return;

        String fingerprint = VpsDeviceIdentity.fingerprint(context);
        String configuration = FIXED_VPS_ENDPOINT + "\n" + token;
        CloudApiClient api = new CloudApiClient(FIXED_VPS_ENDPOINT);

        if (!configuration.equals(boundConfiguration)) {
            api.bindPhone(token, fingerprint);
            boundConfiguration = configuration;
        }

        // Heartbeat keeps the controller online state fresh even if there are no strips.
        api.heartbeatPhone(token, fingerprint);

        JSONArray strips = new JSONArray();
        List<FleetStore.DeviceRecord> devices = fleetStore.list();
        for (FleetStore.DeviceRecord device : devices) {
            JSONObject item = new JSONObject();
            try {
                item.put("client_ref", fleetStore.cloudRef(device.mac));
                item.put("display_name", device.displayName());
                item.put("online", hub.isConnected(device.mac));
                JSONArray outletStates = new JSONArray();
                long now = System.currentTimeMillis();
                for (int outlet = 1; outlet <= 4; outlet++) {
                    OutletRuntimeStore.Snapshot snapshot =
                            runtimeStore.snapshot(device.mac, outlet, now);
                    JSONObject state = new JSONObject();
                    state.put("outlet", outlet);
                    state.put("known", snapshot.known);
                    state.put("on", snapshot.known && snapshot.on);
                    outletStates.put(state);
                }
                item.put("outlet_states", outletStates);
            } catch (Exception error) {
                throw new IOException("Unable to encode strip status", error);
            }
            strips.put(item);
        }
        JSONObject syncResult = api.syncStrips(token, fingerprint, strips);
        JSONArray actions = syncResult.optJSONArray("outlet_actions");
        if (actions != null) {
            for (int i = 0; i < actions.length(); i++) {
                JSONObject action = actions.optJSONObject(i);
                if (action == null) continue;
                String actionId = action.optString("id", "");
                String clientRef = action.optString("client_ref", "");
                int outlet = action.optInt("outlet", 0);
                boolean turnOn = action.optBoolean("on", false);
                if (actionId.isEmpty()) continue;

                String result = "failed";
                String detail;
                FleetStore.DeviceRecord device = fleetStore.findByCloudRef(clientRef);
                if (device == null) {
                    detail = "Unknown local strip reference";
                } else if (outlet < 1 || outlet > 4) {
                    detail = "Invalid outlet";
                } else if (!hub.isConnected(device.mac)) {
                    detail = "Strip is offline on controller phone";
                } else {
                    try {
                        hub.setOutlet(device.mac, outlet, turnOn);
                        result = "success";
                        detail = "Relay request accepted by local controller";
                    } catch (IOException error) {
                        detail = error.getMessage() == null
                                ? error.getClass().getSimpleName() : error.getMessage();
                    }
                }
                api.ack("phone", token, actionId, result, detail);
            }
        }

        prefs.edit()
                .putString(PREF_CLOUD_LAST_STATUS, "ready")
                .putLong(PREF_CLOUD_LAST_SYNC_AT, System.currentTimeMillis())
                .apply();
    }

    public synchronized void invalidateBinding() {
        boundConfiguration = "";
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim();
    }

    @Override
    public synchronized void close() {
        started = false;
        worker.shutdownNow();
    }
}
