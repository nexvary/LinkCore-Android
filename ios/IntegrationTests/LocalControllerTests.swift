import XCTest
import Network
@testable import FGLink
import FGLinkCore

final class LocalControllerTests: XCTestCase {
    func testActualTCPHandshakeAndAcknowledgedControl() async throws {
        let controller = LocalController(port: 31086)
        let listening = expectation(description: "TCP listener ready")
        controller.onReady = { listening.fulfill() }
        controller.onError = { XCTFail("Listener failed: \($0)") }
        let identified = expectation(description: "Strip authenticated and telemetry received")
        let sent = expectation(description: "Outlet command received")
        let mac = "2CE032C7A520"
        let queue = DispatchQueue(label: "fg.fixture.strip")
        let fakeStrip = NWConnection(host: "127.0.0.1", port: 31086, using: .tcp)
        var buffer = FrameBuffer()
        var identityFulfilled = false
        controller.onUpdate = { rows in
            if !identityFulfilled, rows.first?.canControl(1) == true { identityFulfilled = true; identified.fulfill() }
        }
        controller.start()
        defer { fakeStrip.cancel(); controller.stop() }
        func send(_ frame: String) {
            fakeStrip.send(content: Data((frame + "\r\n").utf8), completion: .contentProcessed { _ in })
        }
        func read() {
            fakeStrip.receive(minimumIncompleteLength: 1, maximumLength: 4096) { data, _, complete, error in
                if let data, let frames = try? buffer.append(data) {
                    for frame in frames {
                        if frame == Wire.getInfo {
                            send("up:getinfo:" + (1...4).map { "\($0):0;off;0;off;off;0;00000000;00000000;00000000;on;00;25" }.joined(separator: ":"))
                        } else if frame == "up:onoff:1:on" { send("up:event:onoff:1:on"); sent.fulfill() }
                    }
                }
                if !complete && error == nil { read() }
            }
        }
        await fulfillment(of: [listening], timeout: 10)
        fakeStrip.stateUpdateHandler = { state in
            if case .ready = state { send("up:bootinfo:lgutap;\(mac);\(mac);1.0.66;connect"); read() }
        }
        fakeStrip.start(queue: queue)
        await fulfillment(of: [identified], timeout: 10)
        try await controller.setOutlet(mac: mac, channel: 1, on: true)
        await fulfillment(of: [sent], timeout: 5)
    }
}
