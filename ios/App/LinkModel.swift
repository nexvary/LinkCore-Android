import SwiftUI
import FGLinkCore

enum LinkRoute: String, CaseIterable { case local, vpn, vps }

@MainActor
final class LinkModel: ObservableObject {
    @Published var route: LinkRoute = .local
    @Published var devices: [Strip] = []
    @Published var selectedMAC: String?
    @Published var message = ""
    @Published var busy = false
    @Published var signedIn = false
    @Published var email = EmailSettings()
    @Published var emailLoaded = false
    @Published var pendingMAC: String?
    @Published var history: [Sample] = []
    @Published var language = UserDefaults.standard.string(forKey: "fg.language") ?? "ar" {
        didSet { UserDefaults.standard.set(language, forKey: "fg.language") }
    }
    @Published var server = UserDefaults.standard.string(forKey: "fg.server") ?? DirectClient.defaultServer {
        didSet { UserDefaults.standard.set(server, forKey: "fg.server") }
    }
    private let local = LocalController()
    private var client: DirectClient?
    private var privateAPI: PrivateAPI?
    private var epoch = 0
    private var visible = false
    private var refreshBusy = false
    var arabic: Bool { language == "ar" }
    func t(_ ar: String, _ en: String) -> String { arabic ? ar : en }
    init() {
        local.onUpdate = { [weak self] rows in Task { @MainActor in
            guard let self, self.route == .local, self.visible else { return }
            self.accept(rows)
        } }
        local.onError = { [weak self] error in Task { @MainActor in self?.message = error.localizedDescription } }
    }
    func activate(_ active: Bool) {
        visible = active
        if active && route == .local { local.start() }
        if !active {
            local.stop(); markOffline()
        }
    }
    func switchRoute(_ value: LinkRoute) {
        guard value != route else { return }
        epoch += 1; route = value; local.stop()
        let old = client; client = nil; privateAPI = nil; if let old { Task { await old.logout() } }
        devices = []; selectedMAC = nil; signedIn = false; pendingMAC = nil; busy = false
        emailLoaded = false; email = EmailSettings(); message = ""
        if visible && value == .local { local.start() }
    }
    func login(username: String, password: String) async {
        guard !busy else { return }
        busy = true; message = ""; let current = epoch
        defer { if current == epoch { busy = false } }
        do {
            let value = try DirectClient(server: server)
            try await value.login(username: username, password: password)
            guard current == epoch, route == .vps else { await value.close(); return }
            client = value; signedIn = true; await refresh()
        } catch { if current == epoch { message = error.localizedDescription } }
    }
    func logout() async {
        epoch += 1; let old = client; client = nil; signedIn = false
        privateAPI = nil
        devices = []; selectedMAC = nil; emailLoaded = false; email = EmailSettings(); pendingMAC = nil
        if let old { await old.logout() }
    }
    func connectShare(_ code: String) async {
        guard route == .vpn, !busy else { return }
        busy = true; let current = epoch
        defer { if current == epoch { busy = false } }
        do {
            let api = try PrivateAPI(code: code)
            let rows = try await api.devices()
            guard current == epoch else { return }
            privateAPI = api; signedIn = true; accept(rows)
        } catch { if current == epoch { message = error.localizedDescription } }
    }
    func refresh() async {
        guard visible, !refreshBusy else { return }
        if route == .local { local.refresh(); return }
        if route == .vpn {
            guard let privateAPI else { return }
            refreshBusy = true; defer { refreshBusy = false }; let current = epoch
            do {
                let rows = try await privateAPI.devices()
                guard current == epoch, visible else { return }; accept(rows)
            } catch { if current == epoch { markOffline(); message = error.localizedDescription } }
            return
        }
        guard let client else { return }
        refreshBusy = true; defer { refreshBusy = false }
        let current = epoch
        do {
            let rows = try await client.devices()
            guard current == epoch, visible else { return }; accept(rows)
        } catch {
            guard current == epoch else { return }; markOffline(); message = error.localizedDescription
            if case LinkError.http(401) = error { await logout() }
        }
    }
    func setOutlet(mac: String, channel: Int, on: Bool) async {
        guard visible, pendingMAC == nil, let strip = devices.first(where: { $0.mac == mac }), strip.canControl(channel) else {
            message = LinkError.offline.localizedDescription; return
        }
        let current = epoch; pendingMAC = mac
        defer { if current == epoch { pendingMAC = nil } }
        do {
            if route == .local { try await local.setOutlet(mac: mac, channel: channel, on: on) }
            else if route == .vpn {
                guard let privateAPI else { throw LinkError.offline }
                try await privateAPI.setOutlet(mac: mac, channel: channel, on: on)
            }
            else {
                guard let client else { throw LinkError.offline }
                let result = try await client.setOutlet(mac: mac, outlet: channel, on: on)
                guard result == "confirmed" else { throw LinkError.timedOut }
            }
            guard current == epoch else { return }
            message = t("تم تأكيد الأمر", "Command confirmed"); await refresh()
        } catch {
            guard current == epoch else { return }; message = error.localizedDescription
            if let index = devices.firstIndex(where: { $0.mac == mac }) { devices[index].connected = false }
        }
    }
    func loadEmail() async {
        guard let client else { return }
        let current = epoch
        do { let result = try await client.emailSettings(); guard current == epoch else { return }; email = result; emailLoaded = true }
        catch { if current == epoch { message = error.localizedDescription } }
    }
    func saveEmail(test: Bool = false) async {
        guard let client, emailLoaded, !busy else { return }
        busy = true; defer { busy = false }
        do {
            if test { try await client.testEmail() } else { try await client.saveEmail(email) }
            message = t("تم بنجاح", "Completed")
        } catch { message = error.localizedDescription }
    }
    private func accept(_ rows: [Strip]) {
        devices = rows
        if selectedMAC == nil || !rows.contains(where: { $0.mac == selectedMAC }) { selectedMAC = rows.first?.mac }
        // Session history records real telemetry; never fabricated samples.
        for strip in rows where strip.connected {
            let powers = strip.outlets.compactMap(\.powerW)
            guard !powers.isEmpty else { continue }
            if let last = history.last(where: { $0.mac == strip.mac }), Date().timeIntervalSince(last.date) < 10 { continue }
            history.append(Sample(mac: strip.mac, date: Date(), watts: powers.reduce(0, +)))
        }
        if history.count > 1440 { history.removeFirst(history.count - 1440) }
    }
    private func markOffline() { for index in devices.indices { devices[index].connected = false } }
    struct Sample: Identifiable { let id = UUID(); let mac: String; let date: Date; let watts: Double }
}
