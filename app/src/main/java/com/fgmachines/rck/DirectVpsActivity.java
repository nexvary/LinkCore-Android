package com.fgmachines.rck;

import android.content.Intent;
import android.content.ActivityNotFoundException;
import android.speech.RecognizerIntent;
import androidx.appcompat.app.AlertDialog;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/** Personal-account client for Direct VPS devices and per-outlet permissions. */
public final class DirectVpsActivity extends AppCompatActivity {
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private DirectVpsApiClient client;
    private LinearLayout page, cards, login;
    private TextView message;
    private EditText server, username, password;
    private Button connect;
    private List<DirectVpsApiClient.Device> devices = new ArrayList<>();
    private boolean resumed, fetching, pending, fresh;
    private int generation;
    private String voiceMac;
    private int voiceGeneration;
    private final ActivityResultLauncher<Intent> voiceLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), result -> {
                String target = voiceMac;
                voiceMac = null;
                if (result.getResultCode() != RESULT_OK || result.getData() == null
                        || target == null || voiceGeneration != generation || client == null) return;
                ArrayList<String> phrases = result.getData().getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
                DirectVoiceCommand command = phrases == null || phrases.isEmpty() ? null
                        : DirectVoiceCommand.parse(phrases.get(0));
                if (command == null) { message.setText(R.string.direct_voice_invalid); return; }
                int session = generation;
                new AlertDialog.Builder(this).setTitle(R.string.direct_voice_confirm)
                        .setMessage(target + "\n" + getString(R.string.direct_outlet, command.outlet)
                                + " · " + getString(command.on ? R.string.direct_on : R.string.direct_off))
                        .setNegativeButton(android.R.string.cancel, null)
                        .setPositiveButton(R.string.direct_voice_send, (dialog, which) -> {
                            if (session != generation) return;
                            for (DirectVpsApiClient.Device device : devices) {
                                if (device.mac.equals(target)) { setOutlet(device, command.outlet, command.on); return; }
                            }
                            message.setText(R.string.direct_unavailable);
                        }).show();
            });
    private String setupSuffix;
    private final ActivityResultLauncher<Intent> setupLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    setupSuffix = result.getData().getStringExtra(StripSetupActivity.RESULT_SUFFIX);
                    message.setText(R.string.setup_network_written);
                    refresh(false);
                }
            });
    private String pendingMac;
    private int pendingOutlet;
    private final Runnable poll = () -> refresh(false);

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        DirectVpsViews.applyLanguage(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        page = DirectVpsViews.page(this);
        page.addView(DirectVpsViews.text(this, getString(R.string.direct_title), 24));
        page.addView(DirectVpsViews.text(this, getString(R.string.direct_users_help), 15));
        page.addView(DirectVpsViews.button(this, getString(R.string.direct_switch_mode), v -> {
            startActivity(new Intent(this, ConnectionModeActivity.class));
            finish();
        }));
        login = new LinearLayout(this);
        login.setOrientation(LinearLayout.VERTICAL);
        server = input(R.string.direct_server, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        server.setText(getPreferences(MODE_PRIVATE).getString("server", DirectVpsApiClient.DEFAULT_SERVER));
        username = input(R.string.direct_username, InputType.TYPE_CLASS_TEXT);
        // Old owner selections cannot become personal-account credentials after upgrade.
        boolean oldOwner = getPreferences(MODE_PRIVATE).getInt("login_type", 0) == 1;
        username.setText(oldOwner ? "" : getPreferences(MODE_PRIVATE).getString("username", ""));
        android.content.SharedPreferences.Editor migration = getPreferences(MODE_PRIVATE).edit().remove("login_type");
        if (oldOwner) migration.remove("username");
        migration.apply();
        password = input(R.string.direct_password,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setSaveEnabled(false);
        password.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        connect = DirectVpsViews.button(this, getString(R.string.direct_login), v -> signIn());
        login.addView(connect);
        page.addView(login);
        setupSuffix = getIntent().getStringExtra(StripSetupActivity.RESULT_SUFFIX);
        page.addView(DirectVpsViews.button(this, getString(R.string.setup_strip), v -> {
            Intent intent = new Intent(this, StripSetupActivity.class);
            intent.putExtra(StripSetupActivity.EXTRA_DIRECT, true);
            setupLauncher.launch(intent);
        }));
        Button logout = DirectVpsViews.button(this, getString(R.string.direct_logout), v -> signOut());
        page.addView(logout);
        message = DirectVpsViews.text(this, "", 15);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        page.addView(message);
        page.addView(DirectVpsViews.button(this, getString(R.string.direct_refresh), v -> refresh(false)));
        cards = new LinearLayout(this);
        cards.setOrientation(LinearLayout.VERTICAL);
        page.addView(cards);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(page);
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(scroll, (v, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(
                    androidx.core.view.WindowInsetsCompat.Type.systemBars()
                            | androidx.core.view.WindowInsetsCompat.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        setContentView(scroll);
    }

    private EditText input(int hint, int type) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setTextColor(Color.WHITE);
        field.setHintTextColor(Color.LTGRAY);
        field.setInputType(type);
        field.setSingleLine(true);
        field.setTextDirection(View.TEXT_DIRECTION_LTR);
        field.setSaveEnabled(false);
        login.addView(field);
        return field;
    }

    private void signIn() {
        if (client != null || fetching) return;
        String loginUsername = username.getText().toString().trim();
        String loginPassword = password.getText().toString();
        if (loginUsername.length() < 3 || loginPassword.isEmpty()) {
            message.setText(R.string.direct_login_input_error);
            return;
        }
        try {
            client = DirectVpsApiClient.subscriber(server.getText().toString());
        } catch (IllegalArgumentException e) {
            message.setText(R.string.direct_login_input_error);
            return;
        }
        getPreferences(MODE_PRIVATE).edit().putString("server", server.getText().toString().trim())
                .putString("username", loginUsername).remove("login_type").apply();
        password.setText("");
        connect.setEnabled(false);
        message.setText(R.string.direct_loading);
        fetching = true;
        int session = generation;
        DirectVpsApiClient api = client;
        worker.execute(() -> {
            try {
                api.loginSubscriber(loginUsername, loginPassword);
                main.post(() -> {
                    if (session != generation || isFinishing()) { api.close(); return; }
                    fetching = false;
                    refresh(true);
                });
            } catch (Exception e) {
                main.post(() -> {
                    if (session != generation || isFinishing()) return;
                    signOut();
                    message.setText(errorText(e));
                });
            }
        });
    }

    private void signOut() {
        generation++;
        voiceMac = null;
        main.removeCallbacks(poll);
        if (client != null) {
            DirectVpsApiClient previous = client;
            worker.execute(() -> { try { previous.logoutSubscriber(); } catch (Exception ignored) {} finally { previous.close(); } });
        }
        client = null;
        fetching = pending = fresh = false;
        devices.clear();
        cards.removeAllViews();
        password.setText("");
        login.setVisibility(View.VISIBLE);
        connect.setEnabled(true);
        message.setText(R.string.direct_logged_out);
    }

    private void schedule() {
        main.removeCallbacks(poll);
        if (resumed && client != null && !pending) main.postDelayed(poll, 5000);
    }

    private void refresh(boolean firstLogin) {
        if (client == null || fetching || pending || !resumed) return;
        fetching = true;
        int session = generation;
        DirectVpsApiClient api = client;
        worker.execute(() -> {
            try {
                List<DirectVpsApiClient.Device> latest = api.devices();
                main.post(() -> {
                    if (session != generation || isFinishing()) return;
                    devices = latest;
                    fresh = true;
                    fetching = false;
                    login.setVisibility(View.GONE);
                    if (firstLogin) message.setText(R.string.direct_connected);
                    if (setupSuffix != null) {
                        DirectVpsApiClient.Device configured = null;
                        for (DirectVpsApiClient.Device device : latest) {
                            if (device.mac.endsWith(setupSuffix)) { configured = device; break; }
                        }
                        message.setText(configured == null ? R.string.setup_approval_required
                                : configured.online() ? R.string.setup_device_online : R.string.setup_device_waiting);
                        if (configured != null && configured.online()) setupSuffix = null;
                    }
                    render();
                    schedule();
                });
            } catch (Exception e) {
                main.post(() -> {
                    if (session != generation || isFinishing()) return;
                    fetching = false;
                    fresh = false;
                    int error = errorText(e);
                    if (firstLogin || unauthorized(e)) signOut();
                    message.setText(error);
                    render();
                    schedule();
                });
            }
        });
    }

    private void listen(DirectVpsApiClient.Device device) {
        if (client == null || pending || !fresh || !device.online() || voiceMac != null) return;
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, getResources().getConfiguration().getLocales().get(0).toLanguageTag());
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, getString(R.string.direct_voice_help));
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        voiceMac = device.mac;
        voiceGeneration = generation;
        try { voiceLauncher.launch(intent); }
        catch (ActivityNotFoundException | SecurityException e) {
            voiceMac = null;
            message.setText(R.string.direct_voice_missing);
        }
    }

    private void toggle(DirectVpsApiClient.Device device, int outlet) {
        setOutlet(device, outlet, device.state(outlet).equals("off"));
    }

    private void setOutlet(DirectVpsApiClient.Device device, int outlet, boolean on) {
        if (client == null || pending || !fresh || !device.canControl(outlet)) {
            message.setText(R.string.direct_unavailable);
            return;
        }
        pending = true;
        pendingMac = device.mac;
        pendingOutlet = outlet;
        main.removeCallbacks(poll);
        message.setText(R.string.direct_waiting);
        render();
        int session = generation;
        DirectVpsApiClient api = client;
        worker.execute(() -> {
            String result;
            List<DirectVpsApiClient.Device> latest = null;
            Exception error = null;
            try {
                result = api.setOutlet(device.mac, outlet, on);
            } catch (Exception e) {
                error = e;
                result = "unknown"; // Never retry a POST after ambiguous delivery.
            }
            try { latest = api.devices(); } catch (Exception ignored) { /* stale states disable control */ }
            final String status = result;
            final List<DirectVpsApiClient.Device> updated = latest;
            final Exception failure = error;
            main.post(() -> {
                if (session != generation || isFinishing()) return;
                pending = false;
                fresh = updated != null;
                if (updated != null) devices = updated;
                if (failure != null && unauthorized(failure)) {
                    signOut();
                    message.setText(R.string.direct_auth_error);
                    return;
                }
                message.setText(status.equals("confirmed") ? R.string.direct_confirmed
                        : status.equals("failed") ? R.string.direct_failed
                        : status.equals("timeout") ? R.string.direct_timeout
                        : failure instanceof DirectVpsApiClient.ApiException ? errorText(failure)
                        : R.string.direct_unknown_result);
                render();
                schedule();
            });
        });
    }

    private void render() {
        cards.removeAllViews();
        if (client == null) return;
        if (devices.isEmpty()) cards.addView(DirectVpsViews.text(this, getString(R.string.direct_no_devices), 16));
        for (DirectVpsApiClient.Device device : devices) {
            JSONObject data = device.data;
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(0, DirectVpsViews.dp(this, 18), 0, DirectVpsViews.dp(this, 18));
            card.addView(DirectVpsViews.text(this, "DIRECT VPS · TCP 10086 · " + device.mac, 18));
            card.addView(DirectVpsViews.text(this, getString(fresh && device.online()
                    ? R.string.direct_online : R.string.direct_offline), 16));
            card.addView(DirectVpsViews.text(this, value(data, "model") + " · " + value(data, "firmware")
                    + "\n" + value(data, "peer"), 14));
            card.addView(DirectVpsViews.text(this, getString(R.string.direct_times,
                    time(data.optDouble("connected_at", 0)), time(data.optDouble("last_seen", 0))), 13));
            Button voice = DirectVpsViews.button(this, getString(R.string.direct_voice), v -> listen(device));
            boolean controllable = false;
            for (int channel = 1; channel <= 4; channel++) if (device.canControl(channel)) controllable = true;
            voice.setEnabled(fresh && !pending && controllable);
            card.addView(voice);
            card.addView(DirectVpsViews.text(this, getString(R.string.direct_voice_help), 13));
            org.json.JSONArray allowed = data.optJSONArray("allowed_outlets");
            if (allowed != null && allowed.length() == 0) {
                card.addView(DirectVpsViews.text(this, getString(R.string.direct_view_only), 15));
            }
            for (int n = 1; n <= 4; n++) {
                org.json.JSONArray visible = data.optJSONArray("visible_outlets");
                if (visible != null) {
                    boolean permitted = false;
                    for (int i = 0; i < visible.length(); i++) if (visible.optInt(i) == n) permitted = true;
                    if (!permitted) continue;
                }
                final int channel = n;
                boolean busy = device.pending(n) || (pending && device.mac.equals(pendingMac) && n == pendingOutlet);
                boolean online = fresh && device.online();
                String state = device.state(n);
                String label = getString(busy ? R.string.direct_pending : !online ? R.string.direct_offline
                        : state.equals("on") ? R.string.direct_on : state.equals("off")
                        ? R.string.direct_off : R.string.direct_unknown);
                Button button = DirectVpsViews.button(this,
                        getString(R.string.direct_outlet, n) + "   ⏻ " + label, v -> toggle(device, channel));
                int color = busy ? Color.rgb(131, 85, 0) : !online || state.equals("unknown")
                        ? Color.rgb(57, 67, 77) : state.equals("on") ? Color.rgb(20, 122, 71) : Color.rgb(165, 18, 61);
                button.setBackgroundTintList(ColorStateList.valueOf(color));
                button.setTextColor(Color.WHITE);
                button.setEnabled(online && !pending && device.canControl(n));
                button.setContentDescription(getString(R.string.direct_outlet, n) + ", " + label
                        + ", " + getString(state.equals("on") ? R.string.direct_action_off : R.string.direct_action_on));
                card.addView(button);
                JSONObject o = device.outlet(n);
                card.addView(DirectVpsViews.text(this, value(o, "power_w") + " W · " + value(o, "energy_wh")
                        + " Wh · " + value(o, "temperature_c") + " °C\n"
                        + getString(R.string.direct_protection, value(o, "overload"), value(o, "overheat"),
                        value(o, "event_code")), 13));
            }
            cards.addView(card);
        }
    }

    private String time(double seconds) {
        return seconds > 0 ? DateFormat.getDateTimeInstance().format(new Date((long) (seconds * 1000))) : "—";
    }
    private static String value(JSONObject data, String key) {
        return data.isNull(key) ? "—" : data.optString(key, "—");
    }
    private static boolean unauthorized(Exception e) {
        return e instanceof DirectVpsApiClient.ApiException && ((DirectVpsApiClient.ApiException) e).status == 401;
    }
    private static int errorText(Exception e) {
        if (e instanceof DirectVpsApiClient.ApiException) {
            int code = ((DirectVpsApiClient.ApiException) e).status;
            if (code == 401) return R.string.direct_auth_error;
            if (code == 403) return R.string.direct_denied;
            if (code == 409) return R.string.direct_unavailable;
            if (code == 429) return R.string.direct_rate_limited;
            if (code == 404) return R.string.direct_extension_missing;
        }
        return R.string.direct_network_error;
    }
    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        fresh = false;
        render();
        refresh(false);
    }
    @Override protected void onStop() {
        resumed = false;
        fresh = false;
        main.removeCallbacks(poll);
        super.onStop();
    }
    @Override protected void onDestroy() {
        generation++;
        main.removeCallbacksAndMessages(null);
        if (client != null) client.close();
        worker.shutdownNow();
        super.onDestroy();
    }
}
