package com.fgmachines.rck;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.Locale;

final class DirectVpsViews {
    private DirectVpsViews() {}
    @SuppressWarnings("deprecation")
    static void applyLanguage(Activity activity) {
        String tag = activity.getSharedPreferences("fg_rck_settings", 0).getString("language", "");
        if (tag != null && !tag.isEmpty()) {
            Configuration config = new Configuration(activity.getResources().getConfiguration());
            config.setLocale(Locale.forLanguageTag(tag));
            activity.getResources().updateConfiguration(config, activity.getResources().getDisplayMetrics());
        }
    }
    static int dp(Activity a, int value) { return Math.round(value * a.getResources().getDisplayMetrics().density); }
    static LinearLayout page(Activity a) {
        LinearLayout page = new LinearLayout(a);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setBackgroundColor(Color.rgb(7, 17, 26));
        page.setPadding(dp(a, 20), dp(a, 32), dp(a, 20), dp(a, 24));
        page.setLayoutDirection(a.getResources().getConfiguration().getLayoutDirection());
        android.widget.ImageView logo = new android.widget.ImageView(a);
        logo.setImageResource(R.drawable.fg_link_launcher_v169);
        logo.setContentDescription(a.getString(R.string.app_name));
        page.addView(logo, new LinearLayout.LayoutParams(dp(a, 80), dp(a, 80)));
        return page;
    }
    static TextView text(Activity a, String value, int size) {
        TextView text = new TextView(a);
        text.setText(value);
        text.setTextColor(Color.WHITE);
        text.setTextSize(size);
        text.setPadding(0, dp(a, 8), 0, dp(a, 8));
        return text;
    }
    static Button button(Activity a, String title, View.OnClickListener listener) {
        Button button = new Button(a);
        button.setText(title);
        button.setAllCaps(false);
        button.setTextSize(17);
        button.setMinHeight(dp(a, 56));
        button.setOnClickListener(listener);
        return button;
    }
}
