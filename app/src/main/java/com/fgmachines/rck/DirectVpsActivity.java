package com.fgmachines.rck;

import android.content.Intent;
import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

/** Compatibility entry; Direct VPS now lives inside the Devices tab. */
public final class DirectVpsActivity extends AppCompatActivity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        Intent intent = new Intent(this, MainActivity.class);
        intent.putExtra("open_direct_devices", true);
        intent.putExtra(StripSetupActivity.RESULT_SUFFIX, getIntent().getStringExtra(StripSetupActivity.RESULT_SUFFIX));
        startActivity(intent);
        finish();
    }
}
