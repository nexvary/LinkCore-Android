package com.fgmachines.rck;

import android.Manifest;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import androidx.appcompat.app.AppCompatActivity;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Network configuration only: never registers a MAC, creates a grant or starts a controller. */
public final class StripSetupActivity extends AppCompatActivity {
    public static final String EXTRA_DIRECT = "setup_direct";
    public static final String RESULT_SUFFIX = "setup_suffix";
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private MttlProvisioner provisioner;
    private EditText setupSsid, homeSsid, homePassword, localController;
    private RadioGroup route;
    private RadioButton local, direct;
    private Button automatic, manual, resolve, done;
    private TextView status;
    private CheckBox consent;
    private String directIpv4, configuredSuffix;
    private boolean busy, resolving, written;
    private Runnable permissionAction;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        DirectVpsViews.applyLanguage(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        provisioner = new MttlProvisioner(this);
        LinearLayout page = DirectVpsViews.page(this);
        page.addView(DirectVpsViews.button(this, getString(R.string.setup_back), v -> finish()));
        page.addView(DirectVpsViews.text(this, getString(R.string.setup_strip), 24));
        page.addView(DirectVpsViews.text(this, getString(R.string.setup_instructions), 17));
        route = new RadioGroup(this);
        local = new RadioButton(this); local.setId(View.generateViewId());
        local.setText(R.string.direct_local); local.setTextColor(Color.WHITE);
        direct = new RadioButton(this); direct.setId(View.generateViewId());
        direct.setText(R.string.direct_title); direct.setTextColor(Color.WHITE);
        route.addView(local); route.addView(direct); page.addView(route);
        SharedPreferences prefs = getSharedPreferences("fg_rck_settings", MODE_PRIVATE);
        setupSsid = field(page, R.string.setup_ap_name, false);
        setupSsid.setText(prefs.getString("setup_ssid", ""));
        homeSsid = field(page, R.string.setup_home_name, false);
        homeSsid.setText(prefs.getString("target_ssid", ""));
        homePassword = field(page, R.string.setup_home_password, true);
        localController = field(page, R.string.setup_local_controller, false);
        localController.setText(prefs.getString("hotspot_controller_ip", ""));
        resolve = DirectVpsViews.button(this, getString(R.string.setup_resolve), v -> resolveServer());
        page.addView(resolve);
        consent = new CheckBox(this); consent.setText(R.string.setup_consent); consent.setTextColor(Color.WHITE);
        page.addView(consent);
        page.addView(DirectVpsViews.button(this, getString(R.string.setup_wifi_settings), v ->
                startActivity(new Intent(Settings.ACTION_WIFI_SETTINGS))));
        automatic = DirectVpsViews.button(this, getString(R.string.setup_automatic), v -> requestPermission(false));
        manual = DirectVpsViews.button(this, getString(R.string.setup_manual), v -> requestPermission(true));
        page.addView(automatic); page.addView(manual);
        status = DirectVpsViews.text(this, "", 17);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE); page.addView(status);
        done = DirectVpsViews.button(this, getString(R.string.setup_check_account), v -> complete());
        done.setVisibility(View.GONE); page.addView(done);
        route.setOnCheckedChangeListener((group, id) -> {
            written = false; done.setVisibility(View.GONE);
            boolean vps = id == direct.getId();
            localController.setVisibility(vps ? View.GONE : View.VISIBLE);
            resolve.setVisibility(vps ? View.VISIBLE : View.GONE);
            status.setText(vps ? R.string.setup_resolve_first : R.string.setup_local_preserved);
            if (vps && directIpv4 == null) resolveServer();
        });
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.addView(page);
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(scroll, (v, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(
                    androidx.core.view.WindowInsetsCompat.Type.systemBars() | androidx.core.view.WindowInsetsCompat.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom); return insets;
        });
        setContentView(scroll);
        route.check(getIntent().getBooleanExtra(EXTRA_DIRECT, false) ? direct.getId() : local.getId());
    }

    private EditText field(LinearLayout page, int hint, boolean secret) {
        EditText field = new EditText(this); field.setHint(hint);
        field.setTextColor(Color.WHITE); field.setHintTextColor(Color.LTGRAY); field.setSingleLine(true);
        field.setTextDirection(View.TEXT_DIRECTION_LTR);
        field.setInputType(InputType.TYPE_CLASS_TEXT | (secret ? InputType.TYPE_TEXT_VARIATION_PASSWORD : 0));
        field.setSaveEnabled(false); field.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        page.addView(field); return field;
    }

    private void resolveServer() {
        if (busy || resolving) return;
        resolving = true; resolve.setEnabled(false); status.setText(R.string.setup_resolving);
        worker.execute(() -> {
            String ip = null;
            try { ip = VpsFeatureFlags.resolveDirectControllerIpv4(); } catch (java.io.IOException ignored) { }
            String result = ip;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                resolving = false; resolve.setEnabled(true); directIpv4 = result;
                if (direct.isChecked()) status.setText(result == null ? R.string.setup_resolve_failed : R.string.setup_server_ready);
            });
        });
    }

    private void requestPermission(boolean sequential) {
        if (busy) return;
        String permission = Build.VERSION.SDK_INT >= 33 ? Manifest.permission.NEARBY_WIFI_DEVICES
                : Manifest.permission.ACCESS_FINE_LOCATION;
        if (checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED) { configure(sequential); return; }
        permissionAction = () -> configure(sequential);
        requestPermissions(new String[]{permission}, 21);
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code != 21) return;
        Runnable action = permissionAction; permissionAction = null;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            if (action != null) action.run();
        } else status.setText(R.string.wifi_permission_required);
    }

    private void configure(boolean sequential) {
        boolean vps = direct.isChecked();
        String ap = setupSsid.getText().toString().trim();
        String ssid = homeSsid.getText().toString().trim();
        String password = homePassword.getText().toString();
        String controller = vps ? directIpv4 : localController.getText().toString().trim();
        if (!ap.matches("(?:TONLY_TAP_|ONLY_TAP_)[0-9A-Fa-f]{7}") || ssid.isEmpty()
                || controller == null || controller.isEmpty() || !consent.isChecked()) {
            status.setText(R.string.setup_invalid); return;
        }
        if (vps && resolving) { status.setText(R.string.setup_resolve_first); return; }
        written = false; configuredSuffix = ap.substring(ap.length() - 7).toUpperCase(Locale.ROOT);
        setBusy(true); done.setVisibility(View.GONE);
        MttlProvisioner.Callback callback = new MttlProvisioner.Callback() {
            @Override public void onStatus(String detail) {
                runOnUiThread(() -> { if (!isDestroyed()) status.setText(getString(R.string.provisioning)); });
            }
            @Override public void onComplete() {
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    homePassword.setText(""); written = true; setBusy(false);
                    getSharedPreferences("fg_rck_settings", MODE_PRIVATE).edit()
                            .putString("setup_ssid", ap).putString("target_ssid", ssid).apply();
                    status.setText(vps ? R.string.setup_network_written : R.string.setup_local_written);
                    done.setText(vps ? R.string.setup_check_account : R.string.setup_back);
                    done.setVisibility(View.VISIBLE);
                });
            }
            @Override public void onError(String detail, Throwable error) {
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    setBusy(false); status.setText(getString(R.string.provision_failed, detail));
                });
            }
        };
        if (sequential) provisioner.provisionCurrentWifi(ap, ssid, password, controller, callback);
        else provisioner.provision(ap, ssid, password, controller, callback);
    }

    private void setBusy(boolean value) {
        busy = value;
        for (View view : new View[]{local, direct, setupSsid, homeSsid, homePassword, localController, consent,
                automatic, manual, resolve}) view.setEnabled(!value);
    }

    private void complete() {
        if (!written) return;
        if (direct.isChecked()) {
            Intent result = new Intent().putExtra(RESULT_SUFFIX, configuredSuffix);
            if (getCallingActivity() != null) setResult(RESULT_OK, result);
            else startActivity(new Intent(this, DirectVpsActivity.class).putExtra(RESULT_SUFFIX, configuredSuffix));
        }
        finish();
    }

    @Override protected void onDestroy() {
        permissionAction = null;
        if (provisioner != null) provisioner.close();
        worker.shutdownNow(); super.onDestroy();
    }
}
