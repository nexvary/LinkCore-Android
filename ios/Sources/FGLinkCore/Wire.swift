import Foundation

public enum Wire {
    public static let getInfo = "up:getinfo:all"
    public static func matches(_ text: String, _ pattern: String) -> Bool {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return false }
        return match.range.location == 0 && match.range.length == text.utf16.count
    }
    public static func validMAC(_ mac: String) -> Bool { matches(mac, "^[0-9A-Fa-f]{12}$") }
    public static func command(outlet: Int, on: Bool) throws -> String {
        guard (1...4).contains(outlet) else { throw LinkError.invalidCommand }
        return "up:onoff:\(outlet):\(on ? "on" : "off")"
    }
    public static func boot(_ frame: String) -> (mac: String, firmware: String)? {
        guard frame.hasPrefix("up:bootinfo:") else { return nil }
        let parts = frame.dropFirst(12).split(separator: ";", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 5, parts[0] == "lgutap", validMAC(parts[1]),
              parts[1].uppercased() == parts[2].uppercased(), !parts[3].isEmpty,
              parts[3].count <= 64, parts[4] == "connect" else { return nil }
        return (parts[1].uppercased(), parts[3])
    }
    public static func event(_ frame: String) -> (channel: Int, on: Bool)? {
        guard matches(frame, "^up:(?:event:)?onoff:[1-4]:(?:on|off)$") else { return nil }
        let parts = frame.split(separator: ":")
        return (Int(parts[parts.count - 2])!, parts.last == "on")
    }
    public static func telemetry(_ frame: String) -> [Outlet]? {
        guard frame.hasPrefix("up:getinfo:") else { return nil }
        let parts = frame.dropFirst(11).split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count == 8 else { return nil }
        var rows: [Outlet] = []
        for offset in stride(from: 0, to: 8, by: 2) {
            guard let channel = Int(parts[offset]), (1...4).contains(channel),
                  !rows.contains(where: { $0.channel == channel }) else { return nil }
            let f = parts[offset + 1].split(separator: ";", omittingEmptySubsequences: false).map(String.init)
            guard f.count == 12,
                  [0, 2, 5].allSatisfy({ matches(f[$0], "^[0-9]+$") && Int32(f[$0]) != nil }),
                  [1, 3, 4, 9].allSatisfy({ ["on", "off"].contains(f[$0].lowercased()) }),
                  [6, 7, 8].allSatisfy({ matches(f[$0], "^[0-9A-Fa-f]{8}$") }),
                  matches(f[10], "^[0-9A-Fa-f]{2}$"),
                  matches(f[11], "^-?[0-9]+$"), let temp = Int32(f[11]),
                  let raw = Int32(f[5]), let wh = UInt32(f[6], radix: 16) else { return nil }
            rows.append(Outlet(channel: channel, relay: f[1].lowercased(), powerW: Double(raw) / 1000,
                               energyWh: Double(wh), temperatureC: Double(temp)))
        }
        return rows.sorted { $0.channel < $1.channel }
    }
    public static func setupPassword(_ ssid: String) throws -> String {
        guard matches(ssid, "^(?:TONLY_TAP_|ONLY_TAP_)[0-9A-Fa-f]{7}$") else { throw LinkError.invalidCommand }
        return "LGU_" + ssid.suffix(7).uppercased()
    }
    public static func setupCommands(ssid: String, password: String, controllerIPv4: String) throws -> [String] {
        let octets = controllerIPv4.split(separator: ".", omittingEmptySubsequences: false)
        guard octets.count == 4, octets.allSatisfy({ matches(String($0), "^[0-9]{1,3}$") && (0...255).contains(Int($0) ?? -1) }),
              !ssid.isEmpty, ssid.utf8.count <= 32, password.utf8.count <= 63,
              ![ssid, password].contains(where: { $0.utf8.contains(where: { [0, 10, 13, 58].contains($0) }) })
        else { throw LinkError.invalidCommand }
        return ["up:ip:\(controllerIPv4)", "up:connect:\(ssid):\(password)", "up:reboot:0"]
    }
}

/// Bounded CRLF stream, including the Android firmware's split telemetry records.
public struct FrameBuffer {
    private var bytes = Data()
    private var partial: String?
    public init() {}
    public mutating func append(_ data: Data) throws -> [String] {
        bytes.append(data)
        guard bytes.count <= 16384 else { throw LinkError.invalidResponse }
        var frames: [String] = []
        while let newline = bytes.firstIndex(of: 10) {
            var line = bytes.prefix(upTo: newline)
            if line.last == 13 { line = line.dropLast() }
            guard let text = String(data: line, encoding: .utf8) else { throw LinkError.invalidResponse }
            bytes.removeSubrange(...newline)
            let assembled = (partial ?? "") + text
            guard assembled.utf8.count <= 8192 else { throw LinkError.invalidResponse }
            if assembled.hasPrefix("up:getinfo:"), assembled != Wire.getInfo, Wire.telemetry(assembled) == nil {
                partial = assembled
            } else {
                partial = nil; frames.append(assembled)
            }
        }
        return frames
    }
}
