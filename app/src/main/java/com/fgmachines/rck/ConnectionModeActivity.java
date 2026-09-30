package com.fgmachines.rck;

import android.content.Intent;
import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

/** Launching the Direct screen does not initialize the Android controller. */
public final class ConnectionModeActivity extends AppCompatActivity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        DirectVpsViews.applyLanguage(this);
        android.widget.LinearLayout page = DirectVpsViews.page(this);
        page.addView(DirectVpsViews.text(this, getString(R.string.direct_choose_mode), 24));
        page.addView(DirectVpsViews.text(this, getString(R.string.direct_choose_help), 16));
        page.addView(DirectVpsViews.button(this, getString(R.string.direct_local), v -> {
            startActivity(new Intent(this, MainActivity.class));
            finish();
        }));
        page.addView(DirectVpsViews.button(this, getString(R.string.direct_title), v -> {
            startActivity(new Intent(this, DirectVpsActivity.class));
            finish();
        }));
        android.widget.ScrollView scroll = new android.widget.ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(page);
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(scroll, (v, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        setContentView(scroll);
    }
}
