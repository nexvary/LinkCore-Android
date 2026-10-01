import Foundation

public enum LinkError: Error, LocalizedError {
    case invalidEndpoint, invalidCommand, invalidResponse, http(Int), offline, busy, timedOut, unsupported
    public var errorDescription: String? {
        switch self {
        case .invalidEndpoint: return "Invalid server address / عنوان الخادم غير صالح"
        case .invalidCommand: return "Invalid command / أمر غير صالح"
        case .invalidResponse: return "Unexpected response / استجابة غير متوقعة"
        case .http(let status): return "HTTP \(status)"
        case .offline: return "Device offline or state unknown / الجهاز غير متصل أو حالته غير معروفة"
        case .busy: return "Command already pending / يوجد أمر قيد التنفيذ"
        case .timedOut: return "No confirmation received / لم يصل تأكيد التنفيذ"
        case .unsupported: return "Requires a physical iPhone / يتطلب جهاز آيفون حقيقي"
        }
    }
}

public struct Outlet: Codable, Identifiable, Equatable {
    public let channel: Int
    public var relay: String
    public var powerW: Double?
    public var energyWh: Double?
    public var temperatureC: Double?
    public var id: Int { channel }
    public init(channel: Int, relay: String = "unknown", powerW: Double? = nil,
                energyWh: Double? = nil, temperatureC: Double? = nil) {
        self.channel = channel; self.relay = relay; self.powerW = powerW
        self.energyWh = energyWh; self.temperatureC = temperatureC
    }
    enum CodingKeys: String, CodingKey {
        case channel, relay, powerW = "power_w", energyWh = "energy_wh", temperatureC = "temperature_c"
    }
}

public struct Strip: Codable, Identifiable, Equatable {
    public var mac: String
    public var connected: Bool
    public var controlEnabled: Bool
    public var deviceBusy: Bool
    public var pendingOutlets: [Int]
    public var allowedOutlets: [Int]
    public var outlets: [Outlet]
    public var id: String { mac }
    public init(mac: String, connected: Bool = false, controlEnabled: Bool = false,
                deviceBusy: Bool = false, pendingOutlets: [Int] = [],
                allowedOutlets: [Int] = [], outlets: [Outlet] = []) {
        self.mac = mac; self.connected = connected; self.controlEnabled = controlEnabled
        self.deviceBusy = deviceBusy; self.pendingOutlets = pendingOutlets
        self.allowedOutlets = allowedOutlets; self.outlets = outlets
    }
    public func canControl(_ channel: Int) -> Bool {
        connected && controlEnabled && !deviceBusy && pendingOutlets.isEmpty
            && allowedOutlets.contains(channel)
            && outlets.contains { $0.channel == channel && ["on", "off"].contains($0.relay) }
    }
    enum CodingKeys: String, CodingKey {
        case mac, connected, outlets, controlEnabled = "control_enabled", deviceBusy = "device_busy"
        case pendingOutlets = "pending_outlets", allowedOutlets = "allowed_outlets"
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        mac = try c.decode(String.self, forKey: .mac).uppercased()
        guard Wire.validMAC(mac) else { throw LinkError.invalidResponse }
        connected = try c.decodeIfPresent(Bool.self, forKey: .connected) ?? false
        controlEnabled = try c.decodeIfPresent(Bool.self, forKey: .controlEnabled) ?? false
        deviceBusy = try c.decodeIfPresent(Bool.self, forKey: .deviceBusy) ?? false
        pendingOutlets = try c.decodeIfPresent([Int].self, forKey: .pendingOutlets) ?? []
        allowedOutlets = try c.decodeIfPresent([Int].self, forKey: .allowedOutlets) ?? []
        outlets = try c.decodeIfPresent([Outlet].self, forKey: .outlets) ?? []
        guard outlets.count <= 4, Set(outlets.map(\.channel)).count == outlets.count,
              outlets.allSatisfy({ (1...4).contains($0.channel) }),
              allowedOutlets.allSatisfy({ (1...4).contains($0) }) else { throw LinkError.invalidResponse }
    }
}

public struct EmailSettings: Codable {
    public var email: String
    public var enabled: Bool
    public var powerW: Int
    public var temperatureC: Int
    public var smtpReady: Bool? = nil
    public init(email: String = "", enabled: Bool = false, powerW: Int = 3000, temperatureC: Int = 70) {
        self.email = email; self.enabled = enabled; self.powerW = powerW; self.temperatureC = temperatureC
    }
    enum CodingKeys: String, CodingKey { case email, enabled, powerW = "power_w", temperatureC = "temperature_c", smtpReady = "smtp_ready" }
}
