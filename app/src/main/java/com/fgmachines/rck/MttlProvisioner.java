package com.fgmachines.rck;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.RouteInfo;
import android.net.wifi.WifiNetworkSpecifier;
import android.os.Build;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Pattern;

/** Provisions known MTTL setup APs without the manufacturer cloud. */
public final class MttlProvisioner {
    private static final Pattern IPV4 = Pattern.compile(
            "^(?:(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)\\.){3}(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)$"
    );

    public interface Callback {
        void onStatus(String status);
        void onComplete();
        void onError(String message, Throwable error);
    }

    private final ConnectivityManager connectivity;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicBoolean active = new AtomicBoolean(false);
    private ConnectivityManager.NetworkCallback networkCallback;
    private volatile boolean processBoundToSetupWifi;

    public MttlProvisioner(Context context) {
        Context app = context.getApplicationContext();
        this.connectivity = (ConnectivityManager) app.getSystemService(Context.CONNECTIVITY_SERVICE);
    }

    public boolean isActive() {
        return active.get();
    }

    /** Automatic Android Wi-Fi request path. Useful on devices that really support STA+AP concurrency. */
    public void provision(String setupSsid, String homeSsid, String homePassword,
                          String controllerIp, Callback callback) {
        if (!begin(setupSsid, homeSsid, homePassword, controllerIp, callback)) return;
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            fail(callback, "Automatic setup-AP connection requires Android 10 or newer", null);
            return;
        }

        String setupPassword = ModelCatalog.setupPassword(setupSsid);
        callback.onStatus("Requesting Android Wi-Fi connection to " + setupSsid + "…");
        WifiNetworkSpecifier specifier = new WifiNetworkSpecifier.Builder()
                .setSsid(setupSsid.trim())
                .setWpa2Passphrase(setupPassword)
                .build();

        NetworkRequest request = new NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .setNetworkSpecifier(specifier)
                .build();

        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) {
                bindProcessToSetupWifi(network);
                String setupHost = findSetupHost(network);
                callback.onStatus("Connected to strip setup AP at " + setupHost + ". Writing local controller settings…");
                worker.execute(() -> configure(network, setupHost, homeSsid.trim(), safePassword(homePassword),
                        controllerIp.trim(), callback));
            }

            @Override public void onUnavailable() {
                fail(callback, "Android could not connect to the strip setup AP", null);
            }
        };

        try {
            connectivity.requestNetwork(request, networkCallback, 45_000);
        } catch (SecurityException error) {
            fail(callback, "Nearby Wi-Fi permission is required", error);
        } catch (RuntimeException error) {
            fail(callback, "Could not start setup-AP connection", error);
        }
    }

    /**
     * Single-phone sequential path. The hotspot is saved first, then the user joins
     * TONLY_TAP/ONLY_TAP manually. Android may keep cellular as the default network because
     * the strip AP has no Internet, so this path explicitly finds the Wi-Fi transport,
     * temporarily binds the process to it, discovers the AP gateway and provisions there.
     */
    public void provisionCurrentWifi(String setupSsid, String homeSsid, String homePassword,
                                     String controllerIp, Callback callback) {
        if (!begin(setupSsid, homeSsid, homePassword, controllerIp, callback)) return;
        callback.onStatus("Detecting the current strip Wi-Fi…");
        worker.execute(() -> {
            try {
                Network setupNetwork = findCurrentWifiTransport();
                if (setupNetwork == null) {
                    fail(callback,
                            "No active Wi-Fi transport is visible to the app. Stay connected to TONLY_TAP/ONLY_TAP and try again.",
                            null);
                    return;
                }

                bindProcessToSetupWifi(setupNetwork);
                String setupHost = findSetupHost(setupNetwork);
                callback.onStatus("Wi-Fi detected. Contacting the strip at " + setupHost + ":" + ModelCatalog.SETUP_PORT + "…");

                if (!setupServiceReachable(setupNetwork, setupHost)) {
                    fail(callback,
                            "The phone is on Wi-Fi, but the strip setup service did not answer at "
                                    + setupHost + ":" + ModelCatalog.SETUP_PORT
                                    + ". Keep the strip in setup mode and try again.",
                            null);
                    return;
                }

                callback.onStatus("Strip setup service detected. Writing hotspot and controller settings…");
                configure(setupNetwork, setupHost, homeSsid.trim(), safePassword(homePassword),
                        controllerIp.trim(), callback);
            } catch (Exception error) {
                fail(callback, "Could not use the current strip Wi-Fi connection", error);
            }
        });
    }

    private boolean begin(String setupSsid, String homeSsid, String homePassword,
                          String controllerIp, Callback callback) {
        if (!active.compareAndSet(false, true)) {
            callback.onError("Provisioning is already running", null);
            return false;
        }
        String setupPassword = ModelCatalog.setupPassword(setupSsid);
        if (setupPassword == null) {
            fail(callback, "Unsupported setup SSID. Expected TONLY_TAP_* or ONLY_TAP_*", null);
            return false;
        }
        if (homeSsid == null || homeSsid.trim().isEmpty()) {
            fail(callback, "Target hotspot/Wi-Fi SSID is required", null);
            return false;
        }
        if (homeSsid.contains(":") || (homePassword != null && homePassword.contains(":"))) {
            fail(callback, "':' is not supported in SSID/password by the text provisioning dialect", null);
            return false;
        }
        if (controllerIp == null || !IPV4.matcher(controllerIp.trim()).matches()) {
            fail(callback, "A valid saved controller IPv4 address is required", null);
            return false;
        }
        return true;
    }

    /**
     * Chooses the active Wi-Fi network by transport/link properties rather than by first
     * requiring port 30300 to answer. The previous behaviour mislabeled a reachable Wi-Fi AP
     * as "not connected" whenever the setup socket probe failed.
     */
    private Network findCurrentWifiTransport() {
        Network[] networks = connectivity.getAllNetworks();
        if (networks == null) return null;

        Network best = null;
        int bestScore = Integer.MIN_VALUE;
        for (Network network : networks) {
            NetworkCapabilities caps = connectivity.getNetworkCapabilities(network);
            if (caps == null || !caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue;

            int score = 10;
            if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) score += 30;
            if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) score += 20;

            LinkProperties links = connectivity.getLinkProperties(network);
            if (links != null) {
                for (LinkAddress linkAddress : links.getLinkAddresses()) {
                    InetAddress address = linkAddress.getAddress();
                    if (!(address instanceof Inet4Address)) continue;
                    String host = address.getHostAddress();
                    if (host == null) continue;
                    if (host.startsWith("192.168.1.")) score += 120;
                    else if (isPrivateIpv4(host)) score += 15;
                }
                for (RouteInfo route : links.getRoutes()) {
                    InetAddress gateway = route.getGateway();
                    if (!(gateway instanceof Inet4Address)) continue;
                    String host = gateway.getHostAddress();
                    if (ModelCatalog.SETUP_ADDRESS.equals(host)) score += 160;
                    else if (host != null && isPrivateIpv4(host)) score += 20;
                }
            }

            if (best == null || score > bestScore) {
                best = network;
                bestScore = score;
            }
        }
        return best;
    }

    private String findSetupHost(Network network) {
        LinkProperties links = connectivity.getLinkProperties(network);
        if (links != null) {
            String privateGateway = null;
            for (RouteInfo route : links.getRoutes()) {
                InetAddress gateway = route.getGateway();
                if (!(gateway instanceof Inet4Address)) continue;
                String host = gateway.getHostAddress();
                if (host == null) continue;
                if (ModelCatalog.SETUP_ADDRESS.equals(host)) return host;
                if (privateGateway == null && isPrivateIpv4(host)) privateGateway = host;
            }
            if (privateGateway != null) return privateGateway;
        }
        return ModelCatalog.SETUP_ADDRESS;
    }

    private boolean setupServiceReachable(Network network, String setupHost) {
        for (int attempt = 0; attempt < 4; attempt++) {
            try (Socket socket = network.getSocketFactory().createSocket()) {
                socket.connect(new InetSocketAddress(setupHost, ModelCatalog.SETUP_PORT), 2_000);
                return true;
            } catch (IOException ignored) {
                if (attempt < 3) {
                    try { Thread.sleep(350L); }
                    catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        return false;
                    }
                }
            }
        }
        return false;
    }

    private void configure(Network network, String setupHost, String homeSsid, String homePassword,
                           String controllerIp, Callback callback) {
        try (Socket socket = network.getSocketFactory().createSocket()) {
            socket.connect(new InetSocketAddress(setupHost, ModelCatalog.SETUP_PORT), 7_000);
            socket.setSoTimeout(3_500);

            BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
                    socket.getOutputStream(), StandardCharsets.UTF_8));
            BufferedReader reader = new BufferedReader(new InputStreamReader(
                    socket.getInputStream(), StandardCharsets.UTF_8));

            send(writer, reader, WireCodec.ipPrefix() + controllerIp, true);
            callback.onStatus("Controller address accepted. Sending hotspot/Wi-Fi settings…");
            send(writer, reader, WireCodec.connectPrefix() + homeSsid + ":" + homePassword, true);
            callback.onStatus("Network settings accepted. Rebooting strip…");
            send(writer, reader, WireCodec.reboot(), false);

            finishNetwork();
            active.set(false);
            callback.onComplete();
        } catch (Exception error) {
            fail(callback, "MTTL provisioning failed", error);
        }
    }

    private static void send(BufferedWriter writer, BufferedReader reader,
                             String command, boolean requireResponse) throws IOException {
        writer.write(command);
        writer.write("\r\n");
        writer.flush();
        if (requireResponse) {
            String response = reader.readLine();
            if (response == null) throw new IOException("Device closed the setup connection");
        } else {
            try { reader.readLine(); }
            catch (IOException ignored) { }
        }
    }

    private void bindProcessToSetupWifi(Network network) {
        try {
            processBoundToSetupWifi = connectivity.bindProcessToNetwork(network);
        } catch (RuntimeException ignored) {
            processBoundToSetupWifi = false;
        }
    }

    private static boolean isPrivateIpv4(String host) {
        if (host.startsWith("10.") || host.startsWith("192.168.")) return true;
        if (!host.startsWith("172.")) return false;
        String[] parts = host.split("\\.");
        if (parts.length != 4) return false;
        try {
            int second = Integer.parseInt(parts[1]);
            return second >= 16 && second <= 31;
        } catch (NumberFormatException ignored) {
            return false;
        }
    }

    private static String safePassword(String value) {
        return value == null ? "" : value;
    }

    public void cancel() {
        finishNetwork();
        active.set(false);
    }

    public void close() {
        cancel();
        worker.shutdownNow();
    }

    private void fail(Callback callback, String message, Throwable error) {
        finishNetwork();
        active.set(false);
        callback.onError(message, error);
    }

    private void finishNetwork() {
        if (processBoundToSetupWifi) {
            try { connectivity.bindProcessToNetwork(null); }
            catch (RuntimeException ignored) { }
            processBoundToSetupWifi = false;
        }

        ConnectivityManager.NetworkCallback callback = networkCallback;
        networkCallback = null;
        if (callback != null) {
            try { connectivity.unregisterNetworkCallback(callback); }
            catch (RuntimeException ignored) { }
        }
    }
}
