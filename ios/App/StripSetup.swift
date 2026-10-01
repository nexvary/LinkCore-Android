import Foundation
import Network
import NetworkExtension
import Darwin
import FGLinkCore

@MainActor
final class StripSetup: ObservableObject {
    @Published var busy = false
    @Published var status = ""
    private var connection: NWConnection?
    private var completion: CheckedContinuation<Void, Error>?
    private var timeout: DispatchWorkItem?
    private var commands: [String] = []
    private var response = Data()
    private let queue = DispatchQueue(label: "fg.link.setup")

    func resolveVPS(_ server: String) async throws -> String {
        let url = try DirectClient.normalizeServer(server)
        guard let host = url.host else { throw LinkError.invalidEndpoint }
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                var hints = addrinfo(); hints.ai_family = AF_INET
                var result: UnsafeMutablePointer<addrinfo>?
                guard getaddrinfo(host, nil, &hints, &result) == 0, let first = result else {
                    continuation.resume(throwing: LinkError.invalidEndpoint); return
                }
                defer { freeaddrinfo(first) }
                var bytes = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                let address = first.pointee.ai_addr.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { $0.pointee.sin_addr }
                var ipv4 = address
                guard inet_ntop(AF_INET, &ipv4, &bytes, socklen_t(bytes.count)) != nil else {
                    continuation.resume(throwing: LinkError.invalidEndpoint); return
                }
                let text = String(cString: bytes)
                guard !text.hasPrefix("127."), text != "0.0.0.0", !text.hasPrefix("169.254.") else {
                    continuation.resume(throwing: LinkError.invalidEndpoint); return
                }
                continuation.resume(returning: text)
            }
        }
    }
    func configure(ap: String, ssid: String, password: String, controller: String, joinAutomatically: Bool) async throws {
        try Task.checkCancellation()
        guard !busy else { throw LinkError.busy }
        let setupPassword = try Wire.setupPassword(ap)
        let frames = try Wire.setupCommands(ssid: ssid, password: password, controllerIPv4: controller)
        busy = true; defer { busy = false }
        if joinAutomatically {
            #if targetEnvironment(simulator)
            throw LinkError.unsupported
            #else
            status = "Connecting to strip Wi-Fi / الاتصال بشبكة المشترك"
            let configuration = NEHotspotConfiguration(ssid: ap, passphrase: setupPassword, isWEP: false)
            configuration.joinOnce = true
            do { try await NEHotspotConfigurationManager.shared.apply(configuration) }
            catch {
                let e = error as NSError
                guard e.domain == NEHotspotConfigurationErrorDomain,
                      e.code == NEHotspotConfigurationError.alreadyAssociated.rawValue else { throw error }
            }
            #endif
        }
        status = "Writing network settings / إرسال إعدادات الشبكة"
        try Task.checkCancellation()
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                self.completion = continuation; commands = frames; response = Data()
                let connection = NWConnection(host: "192.168.1.1", port: 30300, using: .tcp)
                self.connection = connection
                connection.stateUpdateHandler = { [weak self] state in Task { @MainActor in
                    guard let self, self.completion != nil else { return }
                    switch state {
                    case .ready: self.sendNext()
                    case .failed(let error): self.finish(.failure(error))
                    default: break
                    }
                } }
                let timeout = DispatchWorkItem { [weak self] in self?.finish(.failure(LinkError.timedOut)) }
                self.timeout = timeout; DispatchQueue.main.asyncAfter(deadline: .now() + 25, execute: timeout)
                connection.start(queue: queue)
            }
        } onCancel: { Task { @MainActor [weak self] in self?.cancel() } }
        status = "Network settings sent. Return to home Wi-Fi; VPS account assignment is separate. / تم إرسال إعدادات الشبكة. عُد لشبكة المنزل؛ ربط الحساب يتم بشكل منفصل."
    }
    func cancel() { finish(.failure(CancellationError())) }
    private func sendNext() {
        guard let connection, !commands.isEmpty, completion != nil else { return }
        let frame = commands.removeFirst(); response = Data()
        connection.send(content: Data((frame + "\r\n").utf8), completion: .contentProcessed { [weak self] error in Task { @MainActor in
            guard let self else { return }
            if let error { self.finish(.failure(error)) }
            else if self.commands.isEmpty { self.finish(.success(())) }
            else { self.readResponse() }
        } })
    }
    private func readResponse() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 1024) { [weak self] data, _, complete, error in Task { @MainActor in
            guard let self, self.completion != nil else { return }
            if let error { self.finish(.failure(error)); return }
            if let data { self.response.append(data) }
            guard self.response.count <= 8192 else { self.finish(.failure(LinkError.invalidResponse)); return }
            if self.response.contains(10) { self.sendNext() }
            else if complete { self.finish(.failure(LinkError.invalidResponse)) }
            else { self.readResponse() }
        } }
    }
    private func finish(_ result: Result<Void, Error>) {
        guard let completion else { return }
        self.completion = nil; timeout?.cancel(); timeout = nil
        connection?.cancel(); connection = nil; commands = []; response = Data()
        completion.resume(with: result)
    }
}
