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
        assertEquals("/panel/api/direct/devices/2CE032C7A520/outlets/4?state=off",
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
    @Test public void rejectsInvalidBasicAuthUsername() {
        assertThrows(IllegalArgumentException.class, () -> new DirectVpsApiClient("https://example.org", "owner:other", "secret"));
        assertThrows(IllegalArgumentException.class, () -> new DirectVpsApiClient("https://example.org", "owner", ""));
    }
    @Test public void httpsCommandUsesOwnerAuthAndFreshConfirmation() throws Exception {
        FakeConnection connection = new FakeConnection(200,
                "{\"source\":\"direct-vps\",\"status\":\"confirmed\",\"ok\":true}");
        DirectVpsApiClient api = new DirectVpsApiClient("https://example.org/panel", "owner", "test-password", url -> {
            assertEquals("https://example.org/panel/api/direct/devices/2CE032C7A520/outlets/1?state=on", url);
            return connection;
        });
        assertEquals("confirmed", api.setOutlet("2CE032C7A520", 1, true));
        assertEquals("POST", connection.getRequestMethod());
        assertEquals("Basic b3duZXI6dGVzdC1wYXNzd29yZA==", connection.getRequestProperty("Authorization"));
        assertFalse(connection.getInstanceFollowRedirects());
        assertFalse(connection.getUseCaches());
        assertEquals(20000, connection.getReadTimeout());
        assertEquals(0, connection.output.size());
        assertTrue(connection.disconnected);
    }
    @Test public void sendingIsNotConfirmationAndTimeoutIsPreserved() throws Exception {
        FakeConnection connection = new FakeConnection(200, "{\"source\":\"direct-vps\",\"status\":\"sent\"}");
        DirectVpsApiClient api = new DirectVpsApiClient("https://example.org", "owner", "test", url -> connection);
        assertThrows(IOException.class, () -> api.setOutlet("2CE032C7A520", 1, true));
        connection.body = "{\"source\":\"direct-vps\",\"status\":\"timeout\",\"ok\":false}";
        assertEquals("timeout", api.setOutlet("2CE032C7A520", 1, true));
    }
    @Test public void rejectsRedirectAndDoesNotRetryOrExposeBody() throws Exception {
        FakeConnection connection = new FakeConnection(302, "secret response");
        int[] opens = {0};
        DirectVpsApiClient api = new DirectVpsApiClient("https://example.org", "owner", "test", url -> {
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
