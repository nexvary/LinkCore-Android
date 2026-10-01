import Foundation
import Network
import FGLinkCore

/// Foreground controller only. iOS suspension is handled by stopping the listener.
final class LocalController: @unchecked Sendable {
    private final class Peer {
        let connection: NWConnection
        var buffer = FrameBuffer()
        var mac: String?
        var lastSeen = Date()
        init(_ connection: NWConnection) { self.connection = connection }
    }
    private let queue = DispatchQueue(label: "fg.link.local")
    private var listener: NWListener?
    private var peers: [ObjectIdentifier: Peer] = [:]
    private var strips: [String: Strip] = [:]
    private var poller: DispatchSourceTimer?
    private var pending: [String: (channel: Int, on: Bool, completion: (Result<Void, Error>) -> Void, deadline: Date)] = [:]
    var onUpdate: (([Strip]) -> Void)?
    var onError: ((Error) -> Void)?

    func start() {
        queue.async { [self] in
            guard listener == nil else { return }
            do {
                let parameters = NWParameters.tcp
                parameters.allowLocalEndpointReuse = true
                let value = try NWListener(using: parameters, on: 10086)
                listener = value
                value.newConnectionHandler = { [weak self] connection in self?.accept(connection) }
                value.stateUpdateHandler = { [weak self] state in
                    if case .failed(let error) = state { self?.onError?(error); self?.stop() }
                }
                value.start(queue: queue)
                let timer = DispatchSource.makeTimerSource(queue: queue)
                timer.schedule(deadline: .now() + 2, repeating: 2)
                timer.setEventHandler { [weak self] in self?.poll() }
                poller = timer; timer.resume()
            } catch { onError?(error) }
        }
    }
    func stop() { queue.async { [self] in
        listener?.cancel(); listener = nil; poller?.cancel(); poller = nil
        let oldPeers = Array(peers.values); peers.removeAll()
        for peer in oldPeers { peer.connection.cancel() }
        let oldPending = pending; pending.removeAll()
        for (_, command) in oldPending { command.completion(.failure(LinkError.offline)) }
        for mac in strips.keys { strips[mac]?.connected = false; strips[mac]?.pendingOutlets = [] }
        publish()
    } }
    func refresh() { queue.async { [self] in poll() } }
    func setOutlet(mac: String, channel: Int, on: Bool) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            queue.async { [self] in
                guard let strip = strips[mac], strip.canControl(channel),
                      let peer = peers.values.first(where: { $0.mac == mac }) else {
                    continuation.resume(throwing: LinkError.offline); return
                }
                guard pending[mac] == nil else { continuation.resume(throwing: LinkError.busy); return }
                do {
                    let frame = try Wire.command(outlet: channel, on: on)
                    pending[mac] = (channel, on, { continuation.resume(with: $0) }, Date().addingTimeInterval(8))
                    strips[mac]?.pendingOutlets = [channel]; publish(); send(frame, peer)
                } catch { continuation.resume(throwing: error) }
            }
        }
    }
    private func accept(_ connection: NWConnection) {
        guard peers.count < 64 else { connection.cancel(); return }
        let peer = Peer(connection); peers[ObjectIdentifier(connection)] = peer
        connection.stateUpdateHandler = { [weak self, weak peer] state in
            guard let self, let peer else { return }
            if case .ready = state { self.receive(peer) }
            if case .failed = state { self.remove(peer) }
            if case .cancelled = state { self.remove(peer) }
        }
        connection.start(queue: queue)
    }
    private func receive(_ peer: Peer) {
        peer.connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self, weak peer] data, _, complete, error in
            guard let self, let peer else { return }
            do {
                if let data {
                    for frame in try peer.buffer.append(data) { self.process(frame, peer) }
                }
                if complete || error != nil { self.remove(peer) } else { self.receive(peer) }
            } catch { self.remove(peer); self.onError?(error) }
        }
    }
    private func process(_ frame: String, _ peer: Peer) {
        if let boot = Wire.boot(frame) {
            for other in Array(peers.values) where other.mac == boot.mac && other !== peer { remove(other) }
            peer.mac = boot.mac; peer.lastSeen = Date()
            strips[boot.mac] = Strip(mac: boot.mac, connected: true, controlEnabled: true, allowedOutlets: [1,2,3,4])
            send(Wire.getInfo, peer); publish(); return
        }
        guard let mac = peer.mac else { return }
        if let telemetry = Wire.telemetry(frame) {
            peer.lastSeen = Date(); strips[mac]?.outlets = telemetry
            if let command = pending[mac], telemetry.contains(where: { $0.channel == command.channel && $0.relay == (command.on ? "on" : "off") }) { confirm(mac) }
            publish()
        } else if let event = Wire.event(frame) {
            // Event is an acknowledgement from the already identified TCP peer.
            peer.lastSeen = Date()
            if let index = strips[mac]?.outlets.firstIndex(where: { $0.channel == event.channel }) {
                strips[mac]?.outlets[index].relay = event.on ? "on" : "off"
            }
            if let command = pending[mac], command.channel == event.channel, command.on == event.on { confirm(mac) }
            send(Wire.getInfo, peer); publish()
        }
    }
    private func confirm(_ mac: String) {
        let command = pending.removeValue(forKey: mac)
        strips[mac]?.pendingOutlets = []; command?.completion(.success(()))
    }
    private func send(_ frame: String, _ peer: Peer) {
        peer.connection.send(content: Data((frame + "\r\n").utf8), completion: .contentProcessed { [weak self, weak peer] error in
            if error != nil, let peer { self?.remove(peer) }
        })
    }
    private func poll() {
        for (mac, command) in Array(pending) where command.deadline < Date() {
            pending.removeValue(forKey: mac); strips[mac]?.pendingOutlets = []
            command.completion(.failure(LinkError.timedOut))
        }
        for peer in Array(peers.values) {
            if Date().timeIntervalSince(peer.lastSeen) > 20 { remove(peer) }
            else if peer.mac != nil { send(Wire.getInfo, peer) }
        }
        publish()
    }
    private func remove(_ peer: Peer) {
        guard peers.removeValue(forKey: ObjectIdentifier(peer.connection)) != nil else { return }
        peer.connection.cancel()
        if let mac = peer.mac {
            strips[mac]?.connected = false; strips[mac]?.pendingOutlets = []
            pending.removeValue(forKey: mac)?.completion(.failure(LinkError.offline)); publish()
        }
    }
    private func publish() { onUpdate?(strips.values.sorted { $0.mac < $1.mac }) }
}
