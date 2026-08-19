import Foundation
import Network

final class LoopbackHTTPFixtureServer: @unchecked Sendable {
    enum ServerError: Error {
        case failedToStart
        case missingPort
    }

    struct Response: Sendable {
        let statusCode: Int
        let body: Data

        static func json(_ object: Any) throws -> Response {
            Response(
                statusCode: 200,
                body: try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
            )
        }
    }

    private final class StartupState: @unchecked Sendable {
        private let lock = NSLock()
        private var result: Result<Void, Error>?

        func store(_ result: Result<Void, Error>) {
            lock.lock()
            defer { lock.unlock() }
            guard self.result == nil else { return }
            self.result = result
        }

        func load() -> Result<Void, Error>? {
            lock.lock()
            defer { lock.unlock() }
            return result
        }
    }

    private let listener: NWListener
    private let queue = DispatchQueue(label: "cn.metauniverse.werewolfstats.ui-tests.fixture-server")
    private let responses: [String: Response]

    private(set) var baseURL: URL!

    init(responses: [String: Response]) throws {
        self.responses = responses
        listener = try NWListener(using: .tcp, on: .any)

        let startupState = StartupState()
        let startupSignal = DispatchSemaphore(value: 0)
        listener.stateUpdateHandler = { state in
            switch state {
            case .ready:
                startupState.store(.success(()))
                startupSignal.signal()
            case .failed(let error):
                startupState.store(.failure(error))
                startupSignal.signal()
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            self?.serve(connection)
        }
        listener.start(queue: queue)

        guard startupSignal.wait(timeout: .now() + 5) == .success else {
            listener.cancel()
            throw ServerError.failedToStart
        }
        if case .failure(let error) = startupState.load() {
            listener.cancel()
            throw error
        }
        guard let port = listener.port,
              let url = URL(string: "http://127.0.0.1:\(port.rawValue)") else {
            listener.cancel()
            throw ServerError.missingPort
        }
        baseURL = url
    }

    func stop() {
        listener.cancel()
    }

    private func serve(_ connection: NWConnection) {
        connection.start(queue: queue)
        receiveRequest(on: connection, accumulated: Data())
    }

    private func receiveRequest(on connection: NWConnection, accumulated: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1_024) { [weak self] data, _, isComplete, error in
            guard let self else {
                connection.cancel()
                return
            }

            var request = accumulated
            if let data { request.append(data) }
            if request.range(of: Data("\r\n\r\n".utf8)) != nil || isComplete || error != nil {
                self.respond(to: request, on: connection)
            } else {
                self.receiveRequest(on: connection, accumulated: request)
            }
        }
    }

    private func respond(to request: Data, on connection: NWConnection) {
        let requestText = String(decoding: request, as: UTF8.self)
        let requestTarget = requestText
            .split(separator: "\r\n", maxSplits: 1)
            .first?
            .split(separator: " ")
            .dropFirst()
            .first
            .map(String.init)
        let path = requestTarget
            .flatMap { URLComponents(string: $0)?.path }
            ?? "/"
        let response = responses[path] ?? Response(
            statusCode: 404,
            body: Data(#"{"error":"fixture route not found"}"#.utf8)
        )
        let reason = response.statusCode == 200 ? "OK" : "Not Found"
        let headers = [
            "HTTP/1.1 \(response.statusCode) \(reason)",
            "Content-Type: application/json; charset=utf-8",
            "Content-Length: \(response.body.count)",
            "Cache-Control: no-store",
            "X-Request-ID: ui-test-fixture",
            "Connection: close",
            "",
            ""
        ].joined(separator: "\r\n")
        var payload = Data(headers.utf8)
        payload.append(response.body)
        connection.send(content: payload, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}

enum LeaderboardUITestFixture {
    static func responses() throws -> [String: LoopbackHTTPFixtureServer.Response] {
        return [
            "/api/competitions": try .json(competitionResponse),
            "/api/dashboard": try .json(dashboardResponse)
        ]
    }

    private static var competitionResponse: [String: Any] {
        let guangzhou: [String: Any] = [
            "competition_name": "排行榜 UI 测试赛",
            "region_name": "广州",
            "series_name": "京城大师赛",
            "summary": "确定性排行榜 fixture",
            "seasons": ["2026 测试赛季"],
            "team_count": 50,
            "player_count": 80,
            "match_count": 100,
            "competition_href": "/competitions?series=ui-test"
        ]
        let shenzhen: [String: Any] = [
            "competition_name": "深圳 UI 测试赛",
            "region_name": "深圳",
            "series_name": "深大联赛",
            "seasons": ["S4"],
            "competition_href": "/competitions?series=sz-test"
        ]
        return [
            "generated_at": "UI 测试数据",
            "view": "grouped",
            "city_groups": [
                ["region_name": "广州", "competition_count": 1, "latest_played_on": "2026-08-17", "cards": [guangzhou]],
                ["region_name": "深圳", "competition_count": 1, "latest_played_on": "2026-08-18", "cards": [shenzhen]]
            ],
            "cards": [guangzhou, shenzhen]
        ]
    }

    private static var dashboardResponse: [String: Any] {
        let sRows = teamRows(prefix: "s", count: 22, firstName: "S服序第一队", firstPoints: "1.00")
        let fRows = teamRows(prefix: "f", count: 23, firstName: "F服序第一队", firstPoints: "2.00")
        return [
            "generated_at": "UI 测试数据",
            "hero": ["featured_label": "排行榜 fixture"],
            "leaderboard_stages": [
                ["key": "all", "label": "全部"],
                ["key": "regular_season", "label": "常规赛"]
            ],
            "leaderboards": [
                "teams": [teamRow(id: "all-team", rank: 1, name: "全部阶段队", points: "99.00")],
                "players": [],
                "mvp": [],
                "svp": []
            ],
            "leaderboards_by_stage": [
                "regular_season": [
                    "teams": [teamRow(id: "aggregate-team", rank: 1, name: "不应显示的聚合队", points: "999.00")],
                    "players": [[
                        "rank": 1,
                        "player_id": "regular-player",
                        "display_name": "常规赛个人第一",
                        "team_name": "测试战队",
                        "games_played": 9,
                        "points_total": "8.50"
                    ]],
                    "mvp": [[
                        "rank": 1,
                        "player_id": "regular-mvp",
                        "display_name": "常规赛 MVP 第一",
                        "team_name": "测试战队",
                        "award_count": 3,
                        "award_label": "MVP",
                        "latest_awarded_on": "2026-07-20"
                    ]],
                    "svp": [[
                        "rank": 1,
                        "player_id": "regular-svp",
                        "display_name": "常规赛 SVP 第一",
                        "team_name": "测试战队",
                        "award_count": 2,
                        "award_label": "SVP",
                        "latest_awarded_on": "2026-07-19"
                    ]]
                ]
            ],
            "team_leaderboard_sections": [
                "regular_season": [
                    ["key": "S", "label": "S组", "title": "S组常规赛榜", "rows": sRows],
                    ["key": "F", "label": "F组", "title": "F组常规赛榜", "rows": fRows]
                ]
            ]
        ]
    }

    private static func teamRows(prefix: String, count: Int, firstName: String, firstPoints: String) -> [[String: Any]] {
        (1...count).map { position in
            var row = teamRow(
                id: "\(prefix)-team-\(position)",
                rank: position,
                name: position == 1 ? firstName : "\(prefix.uppercased())组第\(position)队",
                points: position == 1 ? firstPoints : String(format: "%.2f", Double(100 - position))
            )
            row["badges"] = position == 1
                ? [["text": "直通", "style": "orange", "kind": "progress"]]
                : []
            return row
        }
    }

    private static func teamRow(id: String, rank: Int, name: String, points: String) -> [String: Any] {
        [
            "rank": rank,
            "team_id": id,
            "short_name": name,
            "points_total": points,
            "win_rate": "50.0%",
            "matches_represented": rank + 2
        ]
    }
}

enum PredictionUITestFixture {
    static func responses() throws -> [String: LoopbackHTTPFixtureServer.Response] {
        var responses = try LeaderboardUITestFixture.responses()
        responses["/api/predictions"] = try .json(predictionsResponse)
        let png = Data(base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2Y4sAAAAASUVORK5CYII=")!
        responses["/api/miniprogram/share-code"] = .init(statusCode: 200, body: png)
        return responses
    }

    private static var predictionsResponse: [String: Any] {
        let markets = ["lt_0", "lt_5", "lt_10", "gt_10", "gt_15", "gt_18"].map { key in
            ["key": key, "label": key, "display": "50.0%", "probability": 0.5] as [String: Any]
        }
        let predictions: [[String: Any]] = (1...12).map { index in
            [
                "rank": index,
                "player_id": "prediction-player-\(index)",
                "player_name": "预测选手\(index)",
                "team_name": "测试战队",
                "expected_total": String(format: "%.2f", Double(13 - index)),
                "expected_points": String(format: "%.2f", Double(13 - index)),
                "game_win_displays": ["50.0%", "50.0%", "50.0%"],
                "expected_wins": 1.5,
                "market_probabilities": markets
            ]
        }
        return [
            "days": [
                ["played_on": "2026-08-17", "label": "2026-08-17", "match_count": 3, "player_entry_count": 12, "scenario_published": true],
                ["played_on": "2026-08-16", "label": "2026-08-16", "match_count": 3, "player_entry_count": 12]
            ],
            "selected_day": ["played_on": "2026-08-17", "label": "2026-08-17 比赛日", "match_count": 3, "player_entry_count": 12],
            "predictions": predictions,
            "pagination": ["offset": 0, "limit": 30, "total": 12, "has_more": false],
            "scenario": ["version": "ui-test", "published": true, "roster_size": 12],
            "model_metadata": ["version": "ui-test-model", "simulations": 10_000]
        ]
    }
}
