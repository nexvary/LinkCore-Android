import XCTest
@testable import FGLinkCore
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class CoreTests: XCTestCase {
    let mac = "2CE032C7A520"
    func testIdentificationRejectsWrongModelAndMismatchedIdentity() {
        XCTAssertEqual(Wire.boot("up:bootinfo:lgutap;\(mac);\(mac);1.0.66;connect")?.mac, mac)
        XCTAssertNil(Wire.boot("up:bootinfo:other;\(mac);\(mac);1.0.66;connect"))
        XCTAssertNil(Wire.boot("up:bootinfo:lgutap;\(mac);AAAAAAAAAAAA;1.0.66;connect"))
        XCTAssertNil(Wire.boot("up:bootinfo:lgutap;\(mac);\(mac);;connect"))
    }
    func testTelemetryParsesEnergyAndRejectsDuplicateChannels() throws {
        let frame = telemetry()
        let rows = try XCTUnwrap(Wire.telemetry(frame))
        XCTAssertEqual(rows.count, 4); XCTAssertEqual(rows[0].powerW, 1.234)
        XCTAssertEqual(rows[0].energyWh, 100); XCTAssertEqual(rows[0].temperatureC, 25)
        XCTAssertNil(Wire.telemetry(frame.replacingOccurrences(of: ":2:", with: ":1:")))
        XCTAssertNil(Wire.telemetry(frame.replacingOccurrences(of: "00000064", with: "garbage")))
    }
    func testChunkedAndMultilineFirmwareTelemetry() throws {
        var buffer = FrameBuffer()
        let frame = telemetry()
        let split = frame.index(frame.startIndex, offsetBy: 70)
        XCTAssertTrue(try buffer.append(Data((String(frame[..<split]) + "\r\n").utf8)).isEmpty)
        XCTAssertEqual(try buffer.append(Data((String(frame[split...]) + "\r\n").utf8)), [frame])
        XCTAssertTrue(try buffer.append(Data("up:event:on".utf8)).isEmpty)
        XCTAssertEqual(try buffer.append(Data("off:4:off\r\n".utf8)), ["up:event:onoff:4:off"])
        XCTAssertThrowsError(try buffer.append(Data(repeating: 65, count: 16385)))
    }
    func testNoUSBCommandsAndProvisioningInjection() throws {
        XCTAssertThrowsError(try Wire.command(outlet: 5, on: true))
        XCTAssertEqual(try Wire.setupPassword("TONLY_TAP_2C7A520"), "LGU_2C7A520")
        XCTAssertThrowsError(try Wire.setupCommands(ssid: "wifi\r\nup:reboot:0", password: "secret", controllerIPv4: "192.168.1.2"))
        XCTAssertThrowsError(try Wire.setupCommands(ssid: "wifi\r\nname", password: "secret", controllerIPv4: "192.168.1.2"))
        XCTAssertThrowsError(try Wire.setupCommands(ssid: "wifi", password: "a:b", controllerIPv4: "192.168.1.2"))
        XCTAssertThrowsError(try Wire.setupCommands(ssid: "wifi", password: "secret", controllerIPv4: "999.1.1.1"))
    }
    func testVoiceGrammarArabicEnglishAndAmbiguousRejection() {
        XCTAssertEqual(VoiceCommand.parse("شغّل المخرج الأوّل")?.outlet, 1)
        XCTAssertEqual(VoiceCommand.parse("اطفي المخرج ٤")?.on, false)
        XCTAssertEqual(VoiceCommand.parse("turn outlet two off")?.outlet, 2)
        XCTAssertNil(VoiceCommand.parse("don't turn on outlet one"))
        XCTAssertNil(VoiceCommand.parse("شغل المخرج واحد واثنين"))
        XCTAssertNil(VoiceCommand.parse("maybe turn on outlet one"))
        XCTAssertNil(VoiceCommand.parse("turn on outlet five"))
        XCTAssertNil(VoiceCommand.parse("turn the on outlet one"))
    }
    func testPermissionsFailClosed() throws {
        var strip = Strip(mac: mac, connected: true, controlEnabled: true, allowedOutlets: [1], outlets: [Outlet(channel: 1, relay: "off"), Outlet(channel: 2, relay: "on")])
        XCTAssertTrue(strip.canControl(1)); XCTAssertFalse(strip.canControl(2))
        strip.pendingOutlets = [2]; XCTAssertFalse(strip.canControl(1))
        strip.pendingOutlets = []; strip.outlets[0].relay = "unknown"; XCTAssertFalse(strip.canControl(1))
        let raw = Data("{\"mac\":\"\(mac)\",\"connected\":true,\"outlets\":[{\"channel\":1,\"relay\":\"on\"}]}".utf8)
        XCTAssertFalse(try JSONDecoder().decode(Strip.self, from: raw).canControl(1))
    }
    func testHTTPSOriginAndSafeCommandPath() throws {
        XCTAssertEqual(try DirectClient.normalizeServer("https://link.fgmachines.org/panel/").absoluteString, "https://link.fgmachines.org")
        for bad in ["http://link.fgmachines.org", "https://user:pass@site.test", "https://site.test/?x=1", "https://site.test/#x", "https://site.test/arbitrary", "https://site.test:0"] {
            XCTAssertThrowsError(try DirectClient.normalizeServer(bad))
        }
        XCTAssertEqual(try DirectClient.commandPath(mac: mac.lowercased(), outlet: 4, on: false), "/api/v1/direct/devices/\(mac)/outlets/4?state=off")
        XCTAssertThrowsError(try DirectClient.commandPath(mac: "../../other", outlet: 1, on: true))
    }
    func testAndroidShareCodeAndPrivateNetworkBoundary() throws {
        let profile = try ShareProfile(code: "FGRCK1|http%3A%2F%2F10.10.2.3%3A18086|secret%2Btoken|CONTROL|\(mac)")
        XCTAssertEqual(profile.endpoint.absoluteString, "http://10.10.2.3:18086")
        XCTAssertEqual(profile.token, "secret+token")
        XCTAssertTrue(profile.canControl)
        XCTAssertTrue(ShareProfile.isPrivateIP("100.64.0.1"))
        XCTAssertFalse(ShareProfile.isPrivateIP("100.128.0.1"))
        XCTAssertThrowsError(try ShareProfile(code: "FGRCK1|http%3A%2F%2F8.8.8.8|secret|CONTROL|"))
        XCTAssertThrowsError(try ShareProfile(code: "FGRCK1|http%3A%2F%2F10.1.2.3|secret%0D%0AX|CONTROL|"))
        XCTAssertThrowsError(try ShareProfile(code: "FGRCK1|http%3A%2F%2F10.1.2.3|secret|OWNER|"))
    }
    func testPrivateHTTPRequiresCompleteBoundedJSON() throws {
        let valid = Data("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}".utf8)
        XCTAssertEqual(try PrivateHTTP.body(valid), Data("{}".utf8))
        XCTAssertThrowsError(try PrivateHTTP.body(Data("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 3\r\n\r\n{}".utf8)))
        XCTAssertThrowsError(try PrivateHTTP.body(Data("HTTP/1.1 302 Found\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}".utf8)))
    }
    func testDirectAPIContractWithSessionAndToken() async throws {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [StubProtocol.self]
        let client = try DirectClient(server: "https://fixture.test", session: URLSession(configuration: configuration))
        try await client.login(username: "customer", password: "not-persisted")
        let devices = try await client.devices()
        XCTAssertEqual(devices.first?.mac, mac)
        let result = try await client.setOutlet(mac: mac, outlet: 1, on: true)
        XCTAssertEqual(result, "confirmed")
        await client.logout()
        do { _ = try await client.devices(); XCTFail("Logged out session must not work") }
        catch { XCTAssertTrue(error is LinkError) }
    }
    private func telemetry() -> String {
        "up:getinfo:" + (1...4).map { "\($0):0;on;0;off;off;1234;00000064;00000000;00000000;on;00;25" }.joined(separator: ":")
    }
}

private final class StubProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let token = "fgd_" + String(repeating: "a", count: 43)
        let authorized = request.value(forHTTPHeaderField: "Authorization") == "Bearer " + token
        var status = 200
        let json: String
        if path.hasSuffix("/auth/login") {
            json = "{\"source\":\"direct-vps\",\"access_token\":\"\(token)\"}"
        } else if !authorized { status = 401; json = "{}" }
        else if path.hasSuffix("/devices") {
            json = "{\"source\":\"direct-vps\",\"devices\":[{\"mac\":\"2CE032C7A520\",\"connected\":true,\"control_enabled\":true,\"allowed_outlets\":[1],\"outlets\":[{\"channel\":1,\"relay\":\"off\"}]}]}"
        } else { json = "{\"source\":\"direct-vps\",\"status\":\"confirmed\"}" }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
