import Foundation

enum APIError: Error, LocalizedError, Sendable, Equatable {
    case invalidURL
    case invalidResponse
    case http(status: Int, message: String, requestID: String?)
    case network(String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "接口地址无效。"
        case .invalidResponse: "服务器返回了无法识别的响应。"
        case .http(_, let message, let requestID):
            requestID.map { "\(message)（请求编号 \($0)）" } ?? message
        case .network(let message): message
        case .decoding: "赛事数据格式发生变化，请稍后更新 App。"
        }
    }

    var allowsStaleFallback: Bool {
        switch self {
        case .network: true
        case .http(let status, _, _): status == 408 || status == 429 || status >= 500
        default: false
        }
    }

    var retryable: Bool { allowsStaleFallback }
}

private struct ServerErrorPayload: Decodable {
    let error: String?
    let message: String?
    let detail: String?
}

actor APIClient {
    static let productionBaseURL = URL(string: "https://wolf.metauniverse-cn.xyz")!

    nonisolated let baseURL: URL
    private let session: URLSession
    private let cache: ResponseCache
    private let decoder: JSONDecoder

    init(
        baseURL: URL = APIClient.configuredBaseURL(),
        cache: ResponseCache = ResponseCache(),
        session: URLSession? = nil
    ) {
        self.baseURL = baseURL
        self.cache = cache
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.default
            configuration.timeoutIntervalForRequest = 12
            configuration.timeoutIntervalForResource = 24
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            configuration.urlCache = URLCache(memoryCapacity: 24 * 1_024 * 1_024, diskCapacity: 100 * 1_024 * 1_024)
            self.session = URLSession(configuration: configuration)
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    func get<Value: Decodable & Sendable>(
        _ path: String,
        queryItems: [URLQueryItem] = [],
        as type: Value.Type = Value.self,
        forceRefresh: Bool = false
    ) async throws -> APIResult<Value> {
        let url = try makeURL(path: path, queryItems: queryItems)
        let key = url.absoluteString
        let cached = await cache.response(for: key)

        if !forceRefresh, let cached, await cache.isFresh(cached) {
            return APIResult(value: try decode(type, from: cached.data), isStale: false)
        }

        do {
            let data = try await requestData(url: url, retryLimit: 1)
            let value = try decode(type, from: data)
            await cache.store(data, for: key)
            return APIResult(value: value, isStale: false)
        } catch let error as APIError where error.allowsStaleFallback {
            if let cached {
                return APIResult(value: try decode(type, from: cached.data), isStale: true)
            }
            throw error
        } catch {
            throw error
        }
    }

    func imageData(_ path: String, queryItems: [URLQueryItem] = []) async throws -> Data {
        let url = try makeURL(path: path, queryItems: queryItems)
        return try await requestData(url: url, retryLimit: 1)
    }

    func remoteData(from url: URL) async throws -> Data {
        try await requestData(url: url, retryLimit: 1)
    }

    nonisolated func assetURL(_ path: String?) -> URL? {
        guard let path, !path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        if let absolute = URL(string: path), absolute.scheme != nil { return absolute }
        return URL(string: path.hasPrefix("/") ? path : "/\(path)", relativeTo: baseURL)?.absoluteURL
    }

    nonisolated func canonicalURL(path: String, scope: CompetitionScope?) -> URL? {
        var components = URLComponents(url: baseURL.appendingPathComponent(path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))), resolvingAgainstBaseURL: false)
        components?.queryItems = scope?.queryItems
        return components?.url
    }

    private func requestData(url: URL, retryLimit: Int) async throws -> Data {
        var lastError: APIError?
        for attempt in 0...retryLimit {
            do {
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.timeoutInterval = 12
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
                guard (200..<300).contains(http.statusCode) else {
                    let payload = try? decoder.decode(ServerErrorPayload.self, from: data)
                    let message = payload?.error ?? payload?.message ?? payload?.detail ?? "接口返回 \(http.statusCode)"
                    let requestID = http.value(forHTTPHeaderField: "X-Request-ID")
                    throw APIError.http(status: http.statusCode, message: message, requestID: requestID)
                }
                return data
            } catch is CancellationError {
                throw CancellationError()
            } catch let error as APIError {
                lastError = error
            } catch {
                lastError = .network(error.localizedDescription.contains("timed out") ? "请求超时，请稍后重试。" : "网络连接失败，请检查网络后重试。")
            }
            if attempt < retryLimit, lastError?.retryable == true {
                try await Task.sleep(for: .milliseconds(300 * (attempt + 1)))
                continue
            }
            break
        }
        throw lastError ?? .invalidResponse
    }

    private func decode<Value: Decodable>(_ type: Value.Type, from data: Data) throws -> Value {
        do { return try decoder.decode(type, from: data) }
        catch { throw APIError.decoding(String(describing: error)) }
    }

    private func makeURL(path: String, queryItems: [URLQueryItem]) throws -> URL {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))),
            resolvingAgainstBaseURL: false
        ) else { throw APIError.invalidURL }
        components.queryItems = queryItems.isEmpty ? nil : queryItems.filter { !($0.value ?? "").isEmpty }
        guard let url = components.url else { throw APIError.invalidURL }
        return url
    }

    nonisolated static func configuredBaseURL(arguments: [String] = ProcessInfo.processInfo.arguments) -> URL {
        if let index = arguments.firstIndex(of: "-APIBaseURL"), arguments.indices.contains(index + 1),
           let url = URL(string: arguments[index + 1]) { return url }
        return productionBaseURL
    }
}
