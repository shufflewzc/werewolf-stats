import Foundation
import XCTest
@testable import WerewolfStats

private final class URLProtocolStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private final class LockedCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var storage = 0

    @discardableResult
    func increment() -> Int {
        lock.lock()
        defer { lock.unlock() }
        storage += 1
        return storage
    }

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }
}

private struct StubPayload: Codable, Equatable, Sendable {
    let value: Int
}

final class APIClientTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    func testFreshCacheAvoidsSecondNetworkRequest() async throws {
        let counter = LockedCounter()
        URLProtocolStub.handler = { request in
            _ = counter.increment()
            return (Self.response(for: request, status: 200), Data(#"{"value":1}"#.utf8))
        }
        let client = makeClient(cache: temporaryCache())

        let first = try await client.get("/value", as: StubPayload.self)
        let second = try await client.get("/value", as: StubPayload.self)

        XCTAssertEqual(first.value, StubPayload(value: 1))
        XCTAssertEqual(second.value, StubPayload(value: 1))
        XCTAssertEqual(counter.value, 1)
        XCTAssertFalse(second.isStale)
    }

    func testRetryThenSuccess() async throws {
        let counter = LockedCounter()
        URLProtocolStub.handler = { request in
            let attempt = counter.increment()
            if attempt == 1 {
                return (Self.response(for: request, status: 500), Data(#"{"error":"temporary"}"#.utf8))
            }
            return (Self.response(for: request, status: 200), Data(#"{"value":2}"#.utf8))
        }
        let result = try await makeClient(cache: temporaryCache()).get("/retry", as: StubPayload.self)

        XCTAssertEqual(result.value.value, 2)
        XCTAssertEqual(counter.value, 2)
    }

    func testServerFailureFallsBackToLastSuccessfulPayload() async throws {
        let counter = LockedCounter()
        URLProtocolStub.handler = { request in
            let attempt = counter.increment()
            if attempt == 1 {
                return (Self.response(for: request, status: 200), Data(#"{"value":7}"#.utf8))
            }
            return (Self.response(for: request, status: 503), Data(#"{"error":"offline"}"#.utf8))
        }
        let client = makeClient(cache: temporaryCache())
        _ = try await client.get("/fallback", as: StubPayload.self)
        let fallback = try await client.get("/fallback", as: StubPayload.self, forceRefresh: true)

        XCTAssertEqual(fallback.value.value, 7)
        XCTAssertTrue(fallback.isStale)
        XCTAssertEqual(counter.value, 3, "503 应重试一次后再回退缓存")
    }

    func testClientErrorDoesNotSilentlyUseCacheAndIncludesRequestID() async throws {
        let counter = LockedCounter()
        URLProtocolStub.handler = { request in
            let attempt = counter.increment()
            if attempt == 1 {
                return (Self.response(for: request, status: 200), Data(#"{"value":9}"#.utf8))
            }
            return (Self.response(for: request, status: 404, headers: ["X-Request-ID": "req-404"]), Data(#"{"error":"missing"}"#.utf8))
        }
        let client = makeClient(cache: temporaryCache())
        _ = try await client.get("/missing", as: StubPayload.self)

        do {
            _ = try await client.get("/missing", as: StubPayload.self, forceRefresh: true)
            XCTFail("预期 404 错误")
        } catch let APIError.http(status, message, requestID) {
            XCTAssertEqual(status, 404)
            XCTAssertEqual(message, "missing")
            XCTAssertEqual(requestID, "req-404")
        } catch {
            XCTFail("错误类型不正确：\(error)")
        }
        XCTAssertEqual(counter.value, 2, "4xx 不应重试")
    }

    func testDecodingErrorDoesNotSilentlyUseCache() async throws {
        let counter = LockedCounter()
        URLProtocolStub.handler = { request in
            let attempt = counter.increment()
            let data = attempt == 1 ? Data(#"{"value":3}"#.utf8) : Data(#"{"value":"not-an-int"}"#.utf8)
            return (Self.response(for: request, status: 200), data)
        }
        let client = makeClient(cache: temporaryCache())
        _ = try await client.get("/decode", as: StubPayload.self)

        do {
            _ = try await client.get("/decode", as: StubPayload.self, forceRefresh: true)
            XCTFail("预期解码错误")
        } catch APIError.decoding {
            XCTAssertEqual(counter.value, 2)
        } catch {
            XCTFail("错误类型不正确：\(error)")
        }
    }

    private func makeClient(cache: ResponseCache) -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return APIClient(
            baseURL: URL(string: "https://example.test")!,
            cache: cache,
            session: URLSession(configuration: configuration)
        )
    }

    private func temporaryCache() -> ResponseCache {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        return ResponseCache(freshInterval: 60, directory: directory)
    }

    private static func response(for request: URLRequest, status: Int, headers: [String: String]? = nil) -> HTTPURLResponse {
        HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
    }
}
