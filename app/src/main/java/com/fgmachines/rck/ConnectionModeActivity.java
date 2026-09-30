package com.fgmachines.rck;

import android.content.Intent;
import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

/** Compatibility launcher; connection choices now live inside Devices. */
public final class ConnectionModeActivity extends AppCompatActivity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        startActivity(new Intent(this, MainActivity.class));
        finish();
    }
}
