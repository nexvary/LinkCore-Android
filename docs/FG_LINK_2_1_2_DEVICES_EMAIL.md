# FG Link 2.1.2 (versionCode 47)

Direct VPS is integrated into the Devices tab. Local/LAN/ZeroTier and Direct VPS can be selected there without leaving the app or signing out while navigating other tabs. Existing local profiles and device configuration remain in place. The customer app uses personal Direct accounts only.

Email settings now use the personal Direct account, rather than the unrelated legacy cloud session. Settings include recipient, enabled state, power and temperature thresholds, and a test email. The switch reflects saved server state. SMTP setup and delivery errors are explicit. A test response means the SMTP service accepted the message, not that the recipient inbox necessarily delivered it.

The server monitors granted devices, reports sustained disconnects (120 seconds), protection events, and threshold breaches on visible outlets. It deduplicates active events and does not turn daemon IPC failure into a fake disconnect. Newly registered offline MACs do not produce a false disconnect alert. Adding a MAC does not provision its network or grant ownership automatically.

## Existing Direct server update

Use `server/update-direct-users.sh` with `FG_DIRECT_SOURCE_COMMIT` set to the tested release commit. It requires the existing managed Direct Compose override, backs up application, override, daemon and database, preserves the running database/configuration, and adds the email module and SMTP environment forwarding. This update does not configure an SMTP provider.

Set these values privately in `/opt/fg-link-server/.env` using your mail provider settings:

```
FGRCK_SMTP_HOST=your-provider-host
FGRCK_SMTP_PORT=587
FGRCK_SMTP_USER=your-provider-user
FGRCK_SMTP_PASSWORD=your-provider-app-password
FGRCK_SMTP_FROM=your-approved-sender
FGRCK_SMTP_SECURITY=starttls
```

Use `ssl` and port `465` if required by the provider. Recreate the API service with `docker compose up -d --no-deps api` after changing the environment. SMTP credentials stay on the server and must never be committed or copied into the APK. Then sign into Direct VPS, open Email settings, save the recipient and use Save + test. Without server access and SMTP configuration, live email delivery cannot be verified.
