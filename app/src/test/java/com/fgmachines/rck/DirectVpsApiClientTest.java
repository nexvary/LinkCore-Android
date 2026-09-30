package com.fgmachines.rck;

import org.json.JSONObject;
import org.junit.Test;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.security.cert.Certificate;
import java.nio.charset.StandardCharsets;
import javax.net.ssl.HttpsURLConnection;
import static org.junit.Assert.*;

public class DirectVpsApiClientTest {
    private DirectVpsApiClient.Device device(String extra, String outlets) throws Exception {
        return DirectVpsApiClient.parseDevices(new JSONObject("{\"source\":\"direct-vps\",\"devices\":[{"
                + "\"mac\":\"2ce032c7a520\",\"connected\":true,\"control_enabled\":true,"
                + "\"allowed_outlets\":[1,2,3,4],\"outlets\":" + outlets + extra + "}]}" )).get(0);
    }
    @Test public void canonicalHttpsPanelOrigin() {
        assertEquals("https://link.fgmachines.org", DirectVpsApiClient.normalizeServer("https://link.fgmachines.org/panel/"));
        assertEquals("https://example.org:8443", DirectVpsApiClient.normalizeServer("https://example.org:8443"));
    }
    @Test public void rejectsInsecureOrCredentialBearingUrls() {
        for (String url : new String[]{"http://example.org", "https://user:pass@example.org", "https://example.org/path",
                "https://example.org?token=secret", "https://example.org#secret", "https://example.org:0", "not a url"}) {
            assertThrows(url, IllegalArgumentException.class, () -> DirectVpsApiClient.normalizeServer(url));
        }
    }
    @Test public void validatesCommandRouteWithoutInjection() {
        assertEquals("/api/v1/direct/devices/2CE032C7A520/outlets/4?state=off",
                DirectVpsApiClient.commandPath("2ce032c7a520", 4, false));
        assertThrows(IllegalArgumentException.class, () -> DirectVpsApiClient.commandPath("../admin", 1, true));
        assertThrows(IllegalArgumentException.class, () -> DirectVpsApiClient.commandPath("2CE032C7A520", 5, true));
    }
    @Test public void readsActualDirectSessionAndTelemetry() throws Exception {
        DirectVpsApiClient.Device d = device("", "[{\"channel\":1,\"relay\":\"on\",\"power_w\":0,\"energy_wh\":1,\"temperature_c\":25}]");
        assertEquals("2CE032C7A520", d.mac);
        assertTrue(d.online());
        assertTrue(d.canControl(1));
        assertEquals("on", d.state(1));
        assertEquals(25, d.outlet(1).getInt("temperature_c"));
        assertFalse(d.canControl(2));
    }
    @Test public void ignoresOldAndroidHeartbeatAndUnknownRelay() throws Exception {
        DirectVpsApiClient.Device d = device("", "[{\"channel\":1,\"relay\":\"unknown\"}]");
        assertFalse(d.canControl(1));
        d.data.put("connected", false).put("online", true);
        assertFalse(d.online());
    }
    @Test public void honorsOfflineDisabledPolicyAndPending() throws Exception {
        DirectVpsApiClient.Device d = device("", "[{\"channel\":1,\"relay\":\"off\"}]");
        assertTrue(d.canControl(1));
        d.data.put("pending_outlets", new org.json.JSONArray("[2]"));
        assertFalse(d.canControl(1));
        d.data.remove("pending_outlets");
        d.data.put("allowed_outlets", new org.json.JSONArray("[2,3,4]"));
        assertFalse(d.canControl(1));
        d.data.put("allowed_outlets", new org.json.JSONArray("[1]"));
        d.data.put("control_enabled", false);
        assertFalse(d.canControl(1));
        d.data.put("control_enabled", true).put("connected", false);
        assertFalse(d.canControl(1));
    }
    @Test public void refusesDifferentApiAndMalformedMac() {
        assertThrows(org.json.JSONException.class, () -> DirectVpsApiClient.parseDevices(new JSONObject("{\"source\":\"android\",\"devices\":[]}")));
        assertThrows(org.json.JSONException.class, () -> DirectVpsApiClient.parseDevices(new JSONObject("{\"source\":\"direct-vps\",\"devices\":[{\"mac\":\"bad\"}]}")));
    }
    @Test public void subscriberLoginAndCommandsNeverUseOwnerBasicCredentials() throws Exception {
        String token = "fgd_" + "x".repeat(43);
        java.util.List<FakeConnection> sent = new java.util.ArrayList<>();
        java.util.List<String> paths = new java.util.ArrayList<>();
        DirectVpsApiClient api = DirectVpsApiClient.subscriber("https://example.org", url -> {
            paths.add(url);
            String body = url.endsWith("/auth/login")
                    ? "{\"source\":\"direct-vps\",\"access_token\":\"" + token + "\"}"
                    : url.endsWith("/devices") ? "{\"source\":\"direct-vps\",\"devices\":[]}"
                    : url.endsWith("/auth/logout") ? "{\"ok\":true}"
                    : "{\"source\":\"direct-vps\",\"status\":\"confirmed\"}";
            FakeConnection connection;
            try { connection = new FakeConnection(200, body); } catch (Exception e) { throw new IOException(e); }
            sent.add(connection);
            return connection;
        });
        api.loginSubscriber("alice", "customer-test-password");
        assertNull(sent.get(0).getRequestProperty("Authorization"));
        JSONObject payload = new JSONObject(sent.get(0).output.toString(StandardCharsets.UTF_8.name()));
        assertEquals("alice", payload.getString("username"));
        assertEquals("customer-test-password", payload.getString("password"));
        assertTrue(api.devices().isEmpty());
        assertEquals("Bearer " + token, sent.get(1).getRequestProperty("Authorization"));
        assertEquals("confirmed", api.setOutlet("2CE032C7A520", 1, true));
        assertEquals("https://example.org/api/v1/direct/devices/2CE032C7A520/outlets/1?state=on", paths.get(2));
        api.logoutSubscriber();
        assertEquals("https://example.org/api/v1/direct/auth/logout", paths.get(3));
        assertThrows(IOException.class, api::devices);
        assertEquals(4, sent.size());
    }
    @Test public void deviceBusyDisablesVisibleOutletsAndViewOnlyDeniesControl() throws Exception {
        DirectVpsApiClient.Device d = device("", "[{\"channel\":1,\"relay\":\"off\"}]");
        assertTrue(d.canControl(1));
        d.data.put("device_busy", true);
        assertFalse(d.canControl(1));
        d.data.put("device_busy", false).put("allowed_outlets", new org.json.JSONArray());
        assertFalse(d.canControl(1));
    }
    @Test public void httpsCommandNeverUsesOwnerAuthAndRequiresFreshConfirmation() throws Exception {
        FakeConnection connection = new FakeConnection(200,
                "{\"source\":\"direct-vps\",\"status\":\"confirmed\",\"ok\":true}");
        DirectVpsApiClient api = DirectVpsApiClient.subscriber("https://example.org", url -> {
            assertEquals("https://example.org/api/v1/direct/devices/2CE032C7A520/outlets/1?state=on", url);
            return connection;
        });
        assertEquals("confirmed", api.setOutlet("2CE032C7A520", 1, true));
        assertEquals("POST", connection.getRequestMethod());
        assertNull(connection.getRequestProperty("Authorization"));
        assertFalse(connection.getInstanceFollowRedirects());
        assertFalse(connection.getUseCaches());
        assertEquals(20000, connection.getReadTimeout());
        assertEquals(0, connection.output.size());
        assertTrue(connection.disconnected);
    }
    @Test public void sendingIsNotConfirmationAndTimeoutIsPreserved() throws Exception {
        FakeConnection connection = new FakeConnection(200, "{\"source\":\"direct-vps\",\"status\":\"sent\"}");
        DirectVpsApiClient api = DirectVpsApiClient.subscriber("https://example.org", url -> connection);
        assertThrows(IOException.class, () -> api.setOutlet("2CE032C7A520", 1, true));
        connection.body = "{\"source\":\"direct-vps\",\"status\":\"timeout\",\"ok\":false}";
        assertEquals("timeout", api.setOutlet("2CE032C7A520", 1, true));
    }
    @Test public void rejectsRedirectAndDoesNotRetryOrExposeBody() throws Exception {
        FakeConnection connection = new FakeConnection(302, "secret response");
        int[] opens = {0};
        DirectVpsApiClient api = DirectVpsApiClient.subscriber("https://example.org", url -> {
            opens[0]++;
            return connection;
        });
        IOException failure = assertThrows(IOException.class, () -> api.setOutlet("2CE032C7A520", 1, true));
        assertEquals("HTTP 302", failure.getMessage());
        assertEquals(1, opens[0]);
        assertFalse(connection.getInstanceFollowRedirects());
        assertTrue(connection.disconnected);
        api.close();
        assertThrows(IOException.class, api::devices);
        assertEquals(1, opens[0]);
    }
    @Test public void noPublicOwnerConstructorRemains() {
        assertEquals(0, DirectVpsApiClient.class.getConstructors().length);
        for (java.lang.reflect.Constructor<?> constructor : DirectVpsApiClient.class.getDeclaredConstructors()) {
            assertEquals(2, constructor.getParameterCount());
            assertEquals(String.class, constructor.getParameterTypes()[0]);
            assertEquals(DirectVpsApiClient.ConnectionFactory.class, constructor.getParameterTypes()[1]);
        }
    }

    @Test public void malformedLoginTokenCannotAuthorizeRequests() throws Exception {
        FakeConnection connection = new FakeConnection(200,
                "{\"source\":\"direct-vps\",\"access_token\":\"owner-token\"}");
        DirectVpsApiClient api = DirectVpsApiClient.subscriber("https://example.org", url -> connection);
        assertThrows(IOException.class, () -> api.loginSubscriber("alice", "test-password"));
        assertNull(connection.getRequestProperty("Authorization"));
    }

    @Test public void emailPreferencesUsePersonalTokenAndPutJsonAndPropagateDeliveryFailure() throws Exception {
        String token = "fgd_" + "x".repeat(43);
        java.util.List<FakeConnection> sent = new java.util.ArrayList<>();
        int[] responseCode = {200};
        String[] responseBody = {"{\"source\":\"direct-vps\",\"smtp_ready\":true,\"enabled\":true}"};
        DirectVpsApiClient api = DirectVpsApiClient.subscriber("https://example.org", url -> {
            String body = url.endsWith("/auth/login")
                    ? "{\"source\":\"direct-vps\",\"access_token\":\"" + token + "\"}"
                    : responseBody[0];
            try {
                FakeConnection c = new FakeConnection(responseCode[0], body);
                sent.add(c); return c;
            } catch (Exception e) { throw new IOException(e); }
        });
        api.loginSubscriber("alice", "customer-test-password");
        assertTrue(api.emailSettings().getBoolean("smtp_ready"));
        assertEquals("GET", sent.get(1).getRequestMethod());
        assertEquals("Bearer " + token, sent.get(1).getRequestProperty("Authorization"));
        api.saveEmailSettings("alice@example.com", true, 3200, 75);
        FakeConnection put = sent.get(2);
        assertEquals("PUT", put.getRequestMethod());
        JSONObject payload = new JSONObject(put.output.toString(StandardCharsets.UTF_8.name()));
        assertEquals("alice@example.com", payload.getString("email"));
        assertEquals(3200, payload.getInt("power_w"));
        assertEquals(75, payload.getInt("temperature_c"));
        responseBody[0] = "{\"source\":\"direct-vps\",\"status\":\"queued\"}";
        assertThrows(IOException.class, api::testEmail);
        responseCode[0] = 502;
        assertEquals(502, assertThrows(DirectVpsApiClient.ApiException.class, api::testEmail).status);
        responseCode[0] = 200;
        responseBody[0] = "{\"source\":\"direct-vps\",\"status\":\"sent\"}";
        api.testEmail();
        assertEquals("POST", sent.get(5).getRequestMethod());
        assertEquals("Bearer " + token, sent.get(5).getRequestProperty("Authorization"));
    }

    private static final class FakeConnection extends HttpsURLConnection {
        final int code;
        String body;
        boolean disconnected;
        final ByteArrayOutputStream output = new ByteArrayOutputStream();
        FakeConnection(int code, String body) throws Exception {
            super(new URL("https://example.org"));
            this.code = code;
            this.body = body;
        }
        @Override public int getResponseCode() { return code; }
        @Override public String getContentType() { return "application/json"; }
        @Override public InputStream getInputStream() { return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8)); }
        @Override public OutputStream getOutputStream() { return output; }
        @Override public void disconnect() { disconnected = true; }
        @Override public boolean usingProxy() { return false; }
        @Override public void connect() {}
        @Override public String getCipherSuite() { return "test"; }
        @Override public Certificate[] getLocalCertificates() { return null; }
        @Override public Certificate[] getServerCertificates() { return null; }
    }
}
