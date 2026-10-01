import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

private final class BoundedHTTP: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<(Data, URLResponse), Error>?
    private var session: URLSession?
    private var response: URLResponse?
    private var data = Data()
    private var cancelled = false
    func fetch(_ request: URLRequest) async throws -> (Data, URLResponse) {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                lock.lock()
                if cancelled { lock.unlock(); continuation.resume(throwing: CancellationError()); return }
                self.continuation = continuation
                let config = URLSessionConfiguration.ephemeral
                config.urlCache = nil; config.httpCookieStorage = nil
                config.timeoutIntervalForRequest = 20; config.timeoutIntervalForResource = 25
                let value = URLSession(configuration: config, delegate: self, delegateQueue: nil)
                session = value; let task = value.dataTask(with: request)
                lock.unlock(); task.resume()
            }
        } onCancel: { self.cancel() }
    }
    func cancel() {
        lock.lock(); cancelled = true; lock.unlock()
        finish(.failure(CancellationError()))
    }
    private func finish(_ result: Result<(Data, URLResponse), Error>) {
        lock.lock(); let continuation = self.continuation; self.continuation = nil
        let value = session; session = nil; lock.unlock()
        value?.invalidateAndCancel(); continuation?.resume(with: result)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if response.expectedContentLength > 262144 {
            completionHandler(.cancel); finish(.failure(LinkError.invalidResponse)); return
        }
        self.response = response; completionHandler(.allow)
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard self.data.count + data.count <= 262144 else { finish(.failure(LinkError.invalidResponse)); return }
        self.data.append(data)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error { finish(.failure(error)) }
        else if let response { finish(.success((data, response))) }
        else { finish(.failure(LinkError.invalidResponse)) }
    }
}

public actor DirectClient {
    public static let defaultServer = "https://link.fgmachines.org"
    private let origin: URL
    private let session: URLSession?
    private var token = ""
    private var generation = 0
    private var transfers: [UUID: BoundedHTTP] = [:]
    public init(server: String, session: URLSession? = nil) throws {
        origin = try Self.normalizeServer(server)
        self.session = session
    }
    public static func normalizeServer(_ text: String) throws -> URL {
        guard var c = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              c.scheme?.lowercased() == "https", let host = c.host, !host.isEmpty,
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil,
              c.port == nil || (1...65535).contains(c.port!),
              ["", "/", "/panel", "/panel/"].contains(c.path) else { throw LinkError.invalidEndpoint }
        c.path = ""; c.scheme = "https"
        guard let url = c.url else { throw LinkError.invalidEndpoint }
        return url
    }
    private func request(_ method: String, _ path: String, body: Data? = nil, authenticated: Bool = true) async throws -> Data {
        guard !authenticated || !token.isEmpty else { throw LinkError.http(401) }
        guard let url = URL(string: origin.absoluteString + path) else { throw LinkError.invalidEndpoint }
        var req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)
        req.httpMethod = method; req.httpBody = body
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        if method != "GET" { req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if authenticated { req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        let current = generation
        let data: Data
        let response: URLResponse
        if let session { (data, response) = try await session.data(for: req) }
        else {
            let id = UUID(); let transfer = BoundedHTTP(); transfers[id] = transfer
            defer { transfers.removeValue(forKey: id) }
            (data, response) = try await transfer.fetch(req)
        }
        try Task.checkCancellation()
        guard current == generation else { throw CancellationError() }
        guard let http = response as? HTTPURLResponse else { throw LinkError.invalidResponse }
        if http.statusCode == 401 { token = ""; generation += 1 }
        guard http.statusCode == 200 else { throw LinkError.http(http.statusCode) }
        guard http.value(forHTTPHeaderField: "Content-Type")?.lowercased().contains("application/json") == true,
              data.count <= 262144 else { throw LinkError.invalidResponse }
        return data
    }
    public func login(username: String, password: String) async throws {
        token = ""; generation += 1
        let body = try JSONSerialization.data(withJSONObject: ["username": username, "password": password])
        let data = try await request("POST", "/api/v1/direct/auth/login", body: body, authenticated: false)
        struct Reply: Decodable { let source: String; let access_token: String }
        let reply = try JSONDecoder().decode(Reply.self, from: data)
        guard reply.source == "direct-vps", Wire.matches(reply.access_token, "^fgd_[A-Za-z0-9_-]{43}$")
        else { throw LinkError.invalidResponse }
        token = reply.access_token
    }
    public func logout() async {
        if !token.isEmpty { _ = try? await request("POST", "/api/v1/direct/auth/logout", body: Data()) }
        close()
    }
    public func close() {
        token = ""; generation += 1; session?.invalidateAndCancel()
        for transfer in transfers.values { transfer.cancel() }; transfers.removeAll()
    }
    public func devices() async throws -> [Strip] {
        struct Reply: Decodable { let source: String; let devices: [Strip] }
        let result = try JSONDecoder().decode(Reply.self, from: await request("GET", "/api/v1/direct/devices"))
        guard result.source == "direct-vps", Set(result.devices.map(\.mac)).count == result.devices.count
        else { throw LinkError.invalidResponse }
        return result.devices
    }
    public static func commandPath(mac: String, outlet: Int, on: Bool) throws -> String {
        guard Wire.validMAC(mac), (1...4).contains(outlet) else { throw LinkError.invalidCommand }
        return "/api/v1/direct/devices/\(mac.uppercased())/outlets/\(outlet)?state=\(on ? "on" : "off")"
    }
    public func setOutlet(mac: String, outlet: Int, on: Bool) async throws -> String {
        struct Reply: Decodable { let source: String; let status: String }
        let path = try Self.commandPath(mac: mac, outlet: outlet, on: on)
        let result = try JSONDecoder().decode(Reply.self, from: await request("POST", path, body: Data()))
        guard result.source == "direct-vps", ["confirmed", "failed", "timeout"].contains(result.status)
        else { throw LinkError.invalidResponse }
        return result.status
    }
    public func emailSettings() async throws -> EmailSettings {
        try JSONDecoder().decode(EmailSettings.self, from: await request("GET", "/api/v1/direct/email-settings"))
    }
    public func saveEmail(_ value: EmailSettings) async throws -> EmailSettings {
        guard (100...10000).contains(value.powerW), (30...120).contains(value.temperatureC) else { throw LinkError.invalidCommand }
        var payload = value; payload.smtpReady = nil
        return try JSONDecoder().decode(EmailSettings.self, from: await request("PUT", "/api/v1/direct/email-settings", body: JSONEncoder().encode(payload)))
    }
    public func testEmail() async throws {
        struct Reply: Decodable { let status: String }
        let reply = try JSONDecoder().decode(Reply.self, from: await request("POST", "/api/v1/direct/email-settings/test", body: Data()))
        guard reply.status == "sent" else { throw LinkError.invalidResponse }
    }
}
