import CryptoKit
import Foundation

struct CachedResponse: Codable, Sendable {
    let storedAt: Date
    let data: Data
}

actor ResponseCache {
    private var memory: [String: CachedResponse] = [:]
    private let directory: URL
    let freshInterval: TimeInterval

    init(freshInterval: TimeInterval = 60, directory: URL? = nil) {
        self.freshInterval = freshInterval
        let base = directory ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
        self.directory = base.appendingPathComponent("WerewolfStatsResponses", isDirectory: true)
        try? FileManager.default.createDirectory(at: self.directory, withIntermediateDirectories: true)
    }

    func response(for key: String) -> CachedResponse? {
        if let cached = memory[key] { return cached }
        let url = fileURL(for: key)
        guard let data = try? Data(contentsOf: url),
              let cached = try? JSONDecoder().decode(CachedResponse.self, from: data) else { return nil }
        memory[key] = cached
        return cached
    }

    func isFresh(_ response: CachedResponse, now: Date = .now) -> Bool {
        now.timeIntervalSince(response.storedAt) < freshInterval
    }

    func store(_ data: Data, for key: String) {
        let cached = CachedResponse(storedAt: .now, data: data)
        memory[key] = cached
        guard let encoded = try? JSONEncoder().encode(cached) else { return }
        try? encoded.write(to: fileURL(for: key), options: .atomic)
        pruneIfNeeded()
    }

    func removeAll() {
        memory.removeAll()
        try? FileManager.default.removeItem(at: directory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    private func fileURL(for key: String) -> URL {
        let digest = SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(digest).appendingPathExtension("json")
    }

    private func pruneIfNeeded() {
        guard let urls = try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.contentModificationDateKey, .fileSizeKey]
        ) else { return }
        let values = urls.compactMap { url -> (URL, Date, Int)? in
            guard let resources = try? url.resourceValues(forKeys: [.contentModificationDateKey, .fileSizeKey]) else { return nil }
            return (url, resources.contentModificationDate ?? .distantPast, resources.fileSize ?? 0)
        }
        var total = values.reduce(0) { $0 + $1.2 }
        guard total > 50 * 1_024 * 1_024 else { return }
        for item in values.sorted(by: { $0.1 < $1.1 }) where total > 40 * 1_024 * 1_024 {
            try? FileManager.default.removeItem(at: item.0)
            total -= item.2
        }
    }
}

