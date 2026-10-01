import Foundation

public struct ShareProfile {
    public let endpoint: URL
    public let token: String
    public let role: String
    public let scopeMAC: String
    public var canControl: Bool { role != "VIEW" }
    public init(code: String) throws {
        let raw = code.trimmingCharacters(in: .whitespacesAndNewlines)
        let parts = raw.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
        guard raw.count <= 8192, parts.count == 5, parts[0] == "FGRCK1" else { throw LinkError.invalidCommand }
        func decode(_ value: String) throws -> String {
            guard let value = value.replacingOccurrences(of: "+", with: " ").removingPercentEncoding else { throw LinkError.invalidCommand }
            return value.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let address = try decode(parts[1]); let secret = try decode(parts[2]); let scope = try decode(parts[4])
        guard let c = URLComponents(string: address), ["http", "https"].contains(c.scheme?.lowercased() ?? ""),
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil, ["", "/"].contains(c.path),
              c.port == nil || (1...65535).contains(c.port!), let host = c.host,
              Self.isPrivateIP(host), let url = c.url, !secret.isEmpty,
              secret.utf8.allSatisfy({ $0 > 32 && $0 < 127 }),
              ["VIEW", "CONTROL", "ADMIN"].contains(parts[3]), scope.isEmpty || Wire.validMAC(scope)
        else { throw LinkError.invalidEndpoint }
        endpoint = url; token = secret; role = parts[3]; scopeMAC = scope.uppercased()
    }
    public static func isPrivateIP(_ text: String) -> Bool {
        let host = text.trimmingCharacters(in: CharacterSet(charactersIn: "[]")).lowercased()
        if host == "::1" { return true }
        // Accept only numeric addresses: do not resolve attacker-controlled hostnames.
        if host.contains(":"), Wire.matches(host, "^[0-9a-f:]+$"), host.contains("::") || host.split(separator: ":").count == 8 {
            return host.hasPrefix("fc") || host.hasPrefix("fd") || host.hasPrefix("fe80:")
        }
        let pieces = host.split(separator: ".", omittingEmptySubsequences: false)
        guard pieces.count == 4, pieces.allSatisfy({ Wire.matches(String($0), "^[0-9]{1,3}$") && (0...255).contains(Int($0) ?? -1) }) else { return false }
        let n = pieces.map { Int($0)! }
        return n[0] == 10 || n[0] == 127 || (n[0] == 192 && n[1] == 168)
            || (n[0] == 172 && (16...31).contains(n[1])) || (n[0] == 169 && n[1] == 254)
            || (n[0] == 100 && (64...127).contains(n[1]))
    }
}

public enum PrivateHTTP {
    /// The Android local API sends Content-Length and closes each response.
    public static func body(_ data: Data) throws -> Data {
        guard data.count <= 270336, let delimiter = data.range(of: Data("\r\n\r\n".utf8)),
              delimiter.lowerBound <= 8192, let header = String(data: data[..<delimiter.lowerBound], encoding: .utf8) else { throw LinkError.invalidResponse }
        let lines = header.components(separatedBy: "\r\n")
        let status = lines[0].split(separator: " ")
        guard status.count >= 2, status[0].hasPrefix("HTTP/1."), let code = Int(status[1]) else { throw LinkError.invalidResponse }
        guard code == 200 else { throw LinkError.http(code) }
        var fields: [String: String] = [:]
        for line in lines.dropFirst() {
            let parts = line.split(separator: ":", maxSplits: 1).map(String.init)
            guard parts.count == 2 else { throw LinkError.invalidResponse }
            let key = parts[0].lowercased()
            guard fields[key] == nil else { throw LinkError.invalidResponse }
            fields[key] = parts[1].trimmingCharacters(in: .whitespaces)
        }
        guard fields["content-type"]?.lowercased().contains("application/json") == true,
              fields["transfer-encoding"] == nil,
              let lengthText = fields["content-length"], let length = Int(lengthText), (0...262144).contains(length) else { throw LinkError.invalidResponse }
        let body = Data(data[delimiter.upperBound...])
        guard body.count == length else { throw LinkError.invalidResponse }
        return body
    }
}
