import XCTest
@testable import WerewolfStats

final class CacheAndURLTests: XCTestCase {
    func testResponseCacheFreshnessAndRoundTrip() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let cache = ResponseCache(freshInterval: 60, directory: directory)
        let data = Data("{\"ok\":true}".utf8)
        await cache.store(data, for: "key")

        let response = await cache.response(for: "key")
        let cached = try XCTUnwrap(response)
        XCTAssertEqual(cached.data, data)
        let isFresh = await cache.isFresh(cached)
        XCTAssertTrue(isFresh)
        let justFresh = await cache.isFresh(CachedResponse(storedAt: .now.addingTimeInterval(-59), data: data))
        let expired = await cache.isFresh(CachedResponse(storedAt: .now.addingTimeInterval(-61), data: data))
        XCTAssertTrue(justFresh)
        XCTAssertFalse(expired)
    }

    func testAssetURLNormalization() async throws {
        let client = APIClient(baseURL: URL(string: "https://example.com")!)
        XCTAssertEqual(client.assetURL("assets/a.png")?.absoluteString, "https://example.com/assets/a.png")
        XCTAssertEqual(client.assetURL("/assets/a.png")?.absoluteString, "https://example.com/assets/a.png")
        XCTAssertEqual(client.assetURL("https://cdn.example.com/a.png")?.absoluteString, "https://cdn.example.com/a.png")
    }

    func testDebugBaseURLArgumentOverride() {
        let url = APIClient.configuredBaseURL(arguments: ["App", "-APIBaseURL", "http://127.0.0.1:8000"])
        XCTAssertEqual(url.absoluteString, "http://127.0.0.1:8000")
    }
}
