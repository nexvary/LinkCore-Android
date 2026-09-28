package com.fgmachines.rck;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.Closeable;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Local controller endpoint for MTTL-family devices that connect outbound to the
 * configured controller address. Supports more than one strip at the same time.
 */
public final class MttlControllerServer implements Closeable {
    private static final int MAX_FRAME_CHARS = 64 * 1024;

    public interface Listener {
        void onListening(int port);
        void onDeviceConnected(MttlProtocol.BootInfo bootInfo, String remoteAddress);
        void onDeviceDisconnected(String mac);
        void onOutletState(String mac, MttlProtocol.OutletState state);
        void onTelemetry(String mac, MttlProtocol.Telemetry telemetry);
        void onProtocolFrame(String mac, String frame);
        void onError(String message, Throwable error);
    }

    private final Listener listener;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final Map<String, DeviceConnection> devices = new ConcurrentHashMap<>();
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();

    private volatile ServerSocket serverSocket;

    public MttlControllerServer(Listener listener) {
        this.listener = listener;
    }

    public synchronized void start() throws IOException {
        if (running.get()) return;
        ServerSocket socket = new ServerSocket(ModelCatalog.CONTROLLER_PORT);
        socket.setReuseAddress(true);
        serverSocket = socket;
        running.set(true);
        workers.execute(this::acceptLoop);
        scheduler.scheduleAtFixedRate(this::pollAll, 2, 10, TimeUnit.SECONDS);
        if (listener != null) listener.onListening(ModelCatalog.CONTROLLER_PORT);
    }

    public boolean isRunning() {
        return running.get();
    }

    public List<String> connectedMacs() {
        return new ArrayList<>(devices.keySet());
    }

    public void refresh(String mac) throws IOException {
        DeviceConnection connection = requireDevice(mac);
        connection.send(MttlProtocol.GET_INFO);
    }

    public void setOutlet(String mac, int outlet, boolean on) throws IOException {
        DeviceConnection connection = requireDevice(mac);
        connection.send(MttlProtocol.setOutlet(outlet, on));
    }

    private DeviceConnection requireDevice(String mac) throws IOException {
        if (mac == null) throw new IOException("No MTTL device selected");
        DeviceConnection connection = devices.get(mac.toUpperCase());
        if (connection == null || connection.closed.get()) {
            throw new IOException("MTTL device is offline");
        }
        return connection;
    }

    private void acceptLoop() {
        while (running.get()) {
            try {
                Socket socket = serverSocket.accept();
                socket.setKeepAlive(true);
                socket.setTcpNoDelay(true);
                workers.execute(() -> handle(socket));
            } catch (IOException error) {
                if (running.get()) notifyError("Controller accept failed", error);
            }
        }
    }

    private void handle(Socket socket) {
        DeviceConnection connection = null;
        try {
            connection = new DeviceConnection(socket);
            String pendingGetInfo = null;
            String line;
            while (running.get() && (line = connection.reader.readLine()) != null) {
                if (line.length() > MAX_FRAME_CHARS) throw new IOException("MTTL frame exceeded safety limit");

                String frame;
                if (pendingGetInfo != null) {
                    pendingGetInfo += line;
                    if (pendingGetInfo.length() > MAX_FRAME_CHARS) {
                        throw new IOException("MTTL getinfo frame exceeded safety limit");
                    }
                    if (MttlProtocol.parseGetInfo(pendingGetInfo) == null) continue;
                    frame = pendingGetInfo;
                    pendingGetInfo = null;
                } else {
                    frame = line.trim();
                    if (frame.startsWith(WireCodec.getInfoPrefix()) && MttlProtocol.parseGetInfo(frame) == null) {
                        pendingGetInfo = frame;
                        continue;
                    }
                }

                MttlProtocol.BootInfo boot = MttlProtocol.parseBootInfo(frame);
                if (boot != null) {
                    if (!ModelCatalog.isCompatibleBootModel(boot.model)) {
                        throw new IOException("Unsupported MTTL boot model: " + boot.model);
                    }
                    connection.mac = boot.mac;
                    DeviceConnection replaced = devices.put(boot.mac, connection);
                    if (replaced != null && replaced != connection) replaced.closeQuietly();
                    if (listener != null) {
                        listener.onDeviceConnected(boot, String.valueOf(socket.getRemoteSocketAddress()));
                    }
                    connection.send(MttlProtocol.GET_INFO);
                    continue;
                }

                if (connection.mac == null) {
                    // Ignore pre-identification noise/events rather than trusting an unknown peer.
                    continue;
                }

                MttlProtocol.Telemetry telemetry = MttlProtocol.parseGetInfo(frame);
                if (telemetry != null) {
                    if (listener != null) listener.onTelemetry(connection.mac, telemetry);
                    continue;
                }

                MttlProtocol.OutletState outletState = MttlProtocol.parseOnOff(frame);
                if (outletState != null) {
                    if (listener != null) listener.onOutletState(connection.mac, outletState);
                    continue;
                }

                if (listener != null) listener.onProtocolFrame(connection.mac, frame);
            }
        } catch (IOException error) {
            if (running.get()) notifyError("MTTL connection closed with an error", error);
        } finally {
            if (connection != null) {
                String mac = connection.mac;
                connection.closeQuietly();
                if (mac != null && devices.remove(mac, connection) && listener != null) {
                    listener.onDeviceDisconnected(mac);
                }
            } else {
                try { socket.close(); } catch (IOException ignored) { }
            }
        }
    }

    private void pollAll() {
        if (!running.get()) return;
        for (DeviceConnection connection : devices.values()) {
            try {
                connection.send(MttlProtocol.GET_INFO);
            } catch (IOException error) {
                connection.closeQuietly();
            }
        }
    }

    private void notifyError(String message, Throwable error) {
        if (listener != null) listener.onError(message, error);
    }

    @Override
    public synchronized void close() {
        if (!running.getAndSet(false)) return;
        try {
            if (serverSocket != null) serverSocket.close();
        } catch (IOException ignored) { }
        for (DeviceConnection connection : devices.values()) connection.closeQuietly();
        devices.clear();
        scheduler.shutdownNow();
        workers.shutdownNow();
    }

    private static final class DeviceConnection {
        final Socket socket;
        final BufferedReader reader;
        final BufferedWriter writer;
        final AtomicBoolean closed = new AtomicBoolean(false);
        volatile String mac;

        DeviceConnection(Socket socket) throws IOException {
            this.socket = socket;
            reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
            writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
        }

        synchronized void send(String command) throws IOException {
            if (closed.get()) throw new IOException("Connection is closed");
            writer.write(command);
            writer.write("\r\n");
            writer.flush();
        }

        void closeQuietly() {
            if (!closed.getAndSet(true)) {
                try { socket.close(); } catch (IOException ignored) { }
            }
        }
    }
}
