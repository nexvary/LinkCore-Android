import Foundation
import Network
import FGLinkCore

/// Existing Android-controller share codes over LAN or an externally configured private VPN.
@MainActor
final class PrivateAPI {
    let profile: ShareProfile
    init(code: String) throws { profile = try ShareProfile(code: code) }
    func devices() async throws -> [Strip] {
        struct Row: Decodable {
            let mac: String; let connected: Bool; let telemetry: Telemetry?
            struct Telemetry: Decodable { let outlets: [Reading] }
            struct Reading: Decodable { let channel: Int; let on: Bool; let power_w: Double?; let energy_kwh: Double?; let temperature_c: Double? }
        }
        struct Reply: Decodable { let devices: [Row] }
        let reply = try JSONDecoder().decode(Reply.self, from: await request("GET", path: "/api/v1/devices"))
        return try reply.devices.filter { profile.scopeMAC.isEmpty || $0.mac.uppercased() == profile.scopeMAC }.map { row in
            guard Wire.validMAC(row.mac) else { throw LinkError.invalidResponse }
            let readings = row.telemetry?.outlets ?? []
            guard readings.count <= 4, Set(readings.map(\.channel)).count == readings.count,
                  readings.allSatisfy({ (1...4).contains($0.channel) }) else { throw LinkError.invalidResponse }
            return Strip(mac: row.mac.uppercased(), connected: row.connected, controlEnabled: profile.canControl,
                         allowedOutlets: profile.canControl ? [1,2,3,4] : [], outlets: readings.map {
                Outlet(channel: $0.channel, relay: $0.on ? "on" : "off", powerW: $0.power_w,
                       energyWh: $0.energy_kwh.map { $0 * 1000 }, temperatureC: $0.temperature_c)
            })
        }
    }
    func setOutlet(mac: String, channel: Int, on: Bool) async throws {
        guard profile.canControl, profile.scopeMAC.isEmpty || profile.scopeMAC == mac.uppercased(),
              Wire.validMAC(mac), (1...4).contains(channel) else { throw LinkError.invalidCommand }
        _ = try await request("POST", path: "/api/v1/devices/\(mac.uppercased())/outlets/\(channel)?state=\(on ? "on" : "off")")
        // Local API accepts a command before firmware acknowledgement; verify telemetry separately.
        for _ in 0..<6 {
            try await Task.sleep(nanoseconds: 1_000_000_000)
            if let strip = try await devices().first(where: { $0.mac == mac.uppercased() }),
               strip.connected, strip.outlets.contains(where: { $0.channel == channel && $0.relay == (on ? "on" : "off") }) { return }
        }
        throw LinkError.timedOut
    }
    private func request(_ method: String, path: String) async throws -> Data {
        let transfer = PrivateTransfer()
        let port = profile.endpoint.port ?? (profile.endpoint.scheme == "https" ? 443 : 80)
        guard let host = profile.endpoint.host, let networkPort = NWEndpoint.Port(rawValue: UInt16(port)) else { throw LinkError.invalidEndpoint }
        let authority = (host.contains(":") ? "[\(host)]" : host) + ":\(port)"
        let request = "\(method) \(path) HTTP/1.1\r\nHost: \(authority)\r\nAuthorization: Bearer \(profile.token)\r\nAccept: application/json\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        let raw = try await transfer.fetch(host: host.trimmingCharacters(in: CharacterSet(charactersIn: "[]")), port: networkPort, tls: profile.endpoint.scheme == "https", bytes: Data(request.utf8))
        return try PrivateHTTP.body(raw)
    }
}

@MainActor
private final class PrivateTransfer {
    private var connection: NWConnection?
    private var continuation: CheckedContinuation<Data, Error>?
    private var timeout: DispatchWorkItem?
    private var buffer = Data()
    func fetch(host: String, port: NWEndpoint.Port, tls: Bool, bytes: Data) async throws -> Data {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { c in
                continuation = c
                let connection = NWConnection(host: NWEndpoint.Host(host), port: port, using: tls ? .tls : .tcp)
                self.connection = connection
                connection.stateUpdateHandler = { [weak self] state in Task { @MainActor in
                    guard let self, self.continuation != nil else { return }
                    if case .failed(let error) = state { self.finish(.failure(error)) }
                    if case .ready = state {
                        connection.send(content: bytes, completion: .contentProcessed { error in Task { @MainActor in
                            if let error { self.finish(.failure(error)) } else { self.receive() }
                        } })
                    }
                } }
                let timeout = DispatchWorkItem { [weak self] in self?.finish(.failure(LinkError.timedOut)) }
                self.timeout = timeout; DispatchQueue.main.asyncAfter(deadline: .now() + 10, execute: timeout)
                connection.start(queue: DispatchQueue(label: "fg.link.private"))
            }
        } onCancel: { Task { @MainActor [weak self] in self?.finish(.failure(CancellationError())) } }
    }
    private func receive() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, complete, error in Task { @MainActor in
            guard let self, self.continuation != nil else { return }
            if let error { self.finish(.failure(error)); return }
            if let data { self.buffer.append(data) }
            guard self.buffer.count <= 270336 else { self.finish(.failure(LinkError.invalidResponse)); return }
            if complete { self.finish(.success(self.buffer)) } else { self.receive() }
        } }
    }
    private func finish(_ result: Result<Data, Error>) {
        guard let continuation else { return }
        self.continuation = nil; timeout?.cancel(); connection?.cancel(); connection = nil
        continuation.resume(with: result)
    }
}
