import XCTest
import Network

final class FGLinkUITests: XCTestCase {
    func testArabicEnglishSetupAndLogin() {
        let app = XCUIApplication()
        app.launchArguments = ["-fg.language", "ar"]
        app.launch()
        XCTAssertTrue(app.buttons["languageButton"].waitForExistence(timeout: 10))
        attach(app, "Arabic home")
        app.buttons["languageButton"].tap()
        XCTAssertTrue(app.staticTexts["My strips"].firstMatch.waitForExistence(timeout: 3))
        app.segmentedControls["routePicker"].buttons["Direct VPS"].tap()
        XCTAssertTrue(app.secureTextFields["Password"].exists)
        XCTAssertFalse(app.buttons["signInButton"].isEnabled)
        XCTAssertFalse(app.staticTexts["Owner"].exists)
        attach(app, "English VPS account")
        app.tabBars.buttons["Add"].tap()
        XCTAssertTrue(app.textFields["Home Wi-Fi SSID"].waitForExistence(timeout: 3))
        let send = app.buttons["Join Wi-Fi and configure"]
        XCTAssertFalse(send.isEnabled)
        attach(app, "Setup consent")
        app.tabBars.buttons["About"].tap()
        XCTAssertTrue(app.staticTexts["FG Link 2.1.2"].waitForExistence(timeout: 3))
        attach(app, "About")
    }
    func testConfirmedOutletControlWithSimulatedStrip() {
        let app = XCUIApplication()
        app.launchArguments = ["-fg.language", "en"]
        app.launch()
        XCTAssertTrue(app.buttons["languageButton"].waitForExistence(timeout: 10))
        let fixture = SimulatedStrip()
        fixture.start()
        defer { fixture.stop() }
        let card = app.buttons["stripAABBCCDDEE01"]
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        card.tap()
        let on = app.buttons["outlet1On"]
        XCTAssertTrue(on.waitForExistence(timeout: 5))
        expectation(for: NSPredicate(format: "isEnabled == true"), evaluatedWith: on)
        waitForExpectations(timeout: 5)
        let state = app.staticTexts["outlet1State"]
        XCTAssertEqual(state.label, "Off")
        on.tap()
        expectation(for: NSPredicate(format: "label == %@", "On"), evaluatedWith: state)
        waitForExpectations(timeout: 5)
        XCTAssertTrue(fixture.isOn)
        attach(app, "Simulated strip — confirmed outlet controls")
        let off = app.buttons["outlet1Off"]
        expectation(for: NSPredicate(format: "isEnabled == true"), evaluatedWith: off)
        waitForExpectations(timeout: 5)
        off.tap()
        expectation(for: NSPredicate(format: "label == %@", "Off"), evaluatedWith: state)
        waitForExpectations(timeout: 5)
        XCTAssertFalse(fixture.isOn)
    }
    private func attach(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}

// Test-only TCP peer. It never ships as a fake device in the application.
private final class SimulatedStrip: @unchecked Sendable {
    private let queue = DispatchQueue(label: "fg.ui.simulated-strip")
    private var connection: NWConnection?
    private var stopped = false
    private var pending = Data()
    private var relay = false
    var isOn: Bool { queue.sync { relay } }
    func start() { queue.async { self.connect() } }
    func stop() { queue.sync { stopped = true; connection?.cancel(); connection = nil } }
    private func connect() {
        guard !stopped else { return }
        let peer = NWConnection(host: "127.0.0.1", port: 10086, using: .tcp)
        connection = peer; pending = Data()
        peer.stateUpdateHandler = { [weak self, weak peer] state in
            guard let self, let peer, !self.stopped, self.connection === peer else { return }
            switch state {
            case .ready:
                self.send("up:bootinfo:lgutap;AABBCCDDEE01;AABBCCDDEE01;1.0.66;connect", peer)
                self.receive(peer)
            case .failed, .waiting:
                peer.cancel(); self.connection = nil
                self.queue.asyncAfter(deadline: .now() + 0.25) { self.connect() }
            default: break
            }
        }
        peer.start(queue: queue)
    }
    private func send(_ frame: String, _ peer: NWConnection) {
        peer.send(content: Data((frame + "\r\n").utf8), completion: .contentProcessed { _ in })
    }
    private func telemetry(_ peer: NWConnection) {
        let rows = (1...4).map { channel in
            "\(channel):0;\(channel == 1 && relay ? "on" : "off");0;off;off;0;00000000;00000000;00000000;on;00;25"
        }
        send("up:getinfo:" + rows.joined(separator: ":"), peer)
    }
    private func receive(_ peer: NWConnection) {
        peer.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self, weak peer] data, _, complete, error in
            guard let self, let peer, !self.stopped, self.connection === peer else { return }
            if let data { self.pending.append(data) }
            guard self.pending.count <= 16384 else { peer.cancel(); return }
            while let range = self.pending.range(of: Data([13, 10])) {
                let frame = String(data: self.pending.prefix(upTo: range.lowerBound), encoding: .utf8)
                self.pending.removeSubrange(self.pending.startIndex..<range.upperBound)
                if frame == "up:getinfo:all" { self.telemetry(peer) }
                else if frame == "up:onoff:1:on" || frame == "up:onoff:1:off" {
                    self.relay = frame == "up:onoff:1:on"
                    self.send("up:event:onoff:1:" + (self.relay ? "on" : "off"), peer)
                    self.telemetry(peer)
                }
            }
            if !complete && error == nil { self.receive(peer) }
        }
    }
}
