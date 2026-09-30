package com.fgmachines.rck;

import android.app.Application;

/** Application entry point for release-origin checks before any controller service starts. */
public final class FgLinkApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        ReleaseIntegrity.enforce(this);
    }
}
