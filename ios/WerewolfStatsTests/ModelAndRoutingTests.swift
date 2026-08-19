import XCTest
@testable import WerewolfStats

final class ModelAndRoutingTests: XCTestCase {
    func testMixedScalarDecoding() throws {
        let decoder = JSONDecoder()
        XCTAssertEqual(try decoder.decode(JSONScalar.self, from: Data("\"41.00\"".utf8)).text, "41.00")
        XCTAssertEqual(try decoder.decode(JSONScalar.self, from: Data("5.5".utf8)).text, "5.50")
        XCTAssertEqual(try decoder.decode(JSONScalar.self, from: Data("7".utf8)).text, "7")
    }

    func testCompetitionCardBuildsScopeFromHref() throws {
        let json = #"{"competition_name":"测试赛","region_name":"广州","series_name":"大师赛","seasons":["S2"],"competition_href":"/competitions?region=%E5%B9%BF%E5%B7%9E&series=jcds&competition=x"}"#
        let card = try JSONDecoder().decode(CompetitionCard.self, from: Data(json.utf8))
        let scope = card.scope(for: "S2")
        XCTAssertEqual(scope.competition, "测试赛")
        XCTAssertEqual(scope.series, "jcds")
        XCTAssertEqual(scope.season, "S2")
    }

    func testGroupedCompetitionsUseCanonicalCityOrderAndLegacyFallback() throws {
        let groupedJSON = #"{"view":"grouped","city_groups":[{"region_name":"深圳","competition_count":1,"latest_played_on":"2026-08-18","cards":[{"competition_name":"深大联赛","region_name":"深圳","series_name":"深大联赛","seasons":["S4"]}]},{"region_name":"广州","competition_count":1,"latest_played_on":"2026-08-17","cards":[{"competition_name":"飞行杯","region_name":"广州","series_name":"飞行杯","seasons":["S1"]}]}],"cards":[]}"#
        let grouped = try JSONDecoder().decode(CompetitionResponse.self, from: Data(groupedJSON.utf8))
        XCTAssertEqual(grouped.resolvedCityGroups.map(\.regionName), ["深圳", "广州"])
        XCTAssertEqual(grouped.resolvedCityGroups.first?.cards.first?.competitionName, "深大联赛")

        let legacyJSON = #"{"cards":[{"competition_name":"广州一赛","region_name":"广州","series_name":"A","seasons":[],"latest_played_on":"2026-08-01"},{"competition_name":"深圳赛","region_name":"深圳","series_name":"B","seasons":[],"latest_played_on":"2026-08-03"},{"competition_name":"广州二赛","region_name":"广州","series_name":"C","seasons":[],"latest_played_on":"2026-08-02"}]}"#
        let legacy = try JSONDecoder().decode(CompetitionResponse.self, from: Data(legacyJSON.utf8))
        XCTAssertEqual(legacy.resolvedCityGroups.map(\.regionName), ["广州", "深圳"])
        XCTAssertEqual(legacy.resolvedCityGroups[0].cards.map(\.competitionName), ["广州一赛", "广州二赛"])
        XCTAssertEqual(legacy.resolvedCityGroups[0].latestPlayedOn, "2026-08-02")
    }

    @MainActor
    func testScopeAndFavoritesPersist() throws {
        let suite = "ModelAndRoutingTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let scope = CompetitionScope(competition: "公开赛", season: "S2", region: "广州", series: "jcds", seriesName: "京城大师赛")

        let first = AppState(api: APIClient(), defaults: defaults)
        first.selectedScope = scope
        first.toggleFavorite("player-1")

        let restored = AppState(api: APIClient(), defaults: defaults)
        XCTAssertEqual(restored.selectedScope, scope)
        XCTAssertTrue(restored.isFavorite("player-1"))
    }

    @MainActor
    func testDeepLinkRoutesToPlayerAndRestoresScope() throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "DeepLinkTests.\(UUID().uuidString)"))
        let app = AppState(api: APIClient(), defaults: defaults)
        let url = try XCTUnwrap(URL(string: "https://wolf.metauniverse-cn.xyz/players/player-1?competition=%E5%85%AC%E5%BC%80%E8%B5%9B&season=S2&region=%E5%B9%BF%E5%B7%9E&series=jcds"))

        XCTAssertTrue(app.handleDeepLink(url))
        XCTAssertEqual(app.selectedTab, .players)
        XCTAssertEqual(app.selectedScope?.competition, "公开赛")
        XCTAssertEqual(app.tabRouter.router(for: .players).path, [.player("player-1")])
    }

    func testPlayerFixtureDecodes() throws {
        let json = #"{"player":{"player_id":"p1","name":"小鱼","photo":"/assets/a.png","team_name":"洵岛","rank":1,"owner":"未绑定账号","is_star_player":false,"power_rating":{"grade":"S","score":93.3,"source_label":"系统评级"}},"metrics":[{"label":"积分","value":"41.00","copy":"总积分"}],"insights":{"overall_win_rate":"58.3%","mvp_count":1},"recent_matches":[],"achievements":[],"roles":[],"dimension":{"available":false,"reason":"暂无"}}"#
        let payload = try JSONDecoder().decode(PlayerDetailResponse.self, from: Data(json.utf8))
        XCTAssertEqual(payload.player.name, "小鱼")
        XCTAssertEqual(payload.metrics?.first?.value.text, "41.00")
        XCTAssertEqual(payload.player.powerRating?.grade, "S")
    }

    func testAllEndpointResponseFixturesDecode() throws {
        let decoder = JSONDecoder()
        XCTAssertNoThrow(try decoder.decode(CompetitionResponse.self, from: Data(#"{"cards":[]}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(DashboardResponse.self, from: Data(#"{}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(GuildsResponse.self, from: Data(#"{"cards":[]}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(GuildDetailResponse.self, from: Data(#"{"guild":{"guild_id":"g1","name":"门派"}}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(PlayersResponse.self, from: Data(#"{"players":[]}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(TeamsResponse.self, from: Data(#"{"teams":[]}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(TeamDetailResponse.self, from: Data(#"{"team":{"team_id":"t1","name":"战队"}}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(MatchDetailResponse.self, from: Data(#"{"match":{"match_id":"m1"}}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(DayDetailResponse.self, from: Data(#"{}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(PredictionsResponse.self, from: Data(#"{"predictions":[]}"#.utf8)))
        XCTAssertNoThrow(try decoder.decode(SearchResponse.self, from: Data(#"{"results":[]}"#.utf8)))
    }

    func testPredictionLatestFieldsAndShareReadiness() throws {
        let markets = PredictionsResponse.requiredShareMarketKeys.map { key in
            ["key": key, "label": key, "display": "50.0%"]
        }
        let predictions: [[String: Any]] = (1...12).map { index in
            [
                "rank": index,
                "player_id": "p\(index)",
                "player_name": "选手\(index)",
                "expected_total": "8.00",
                "market_probabilities": markets,
                "is_star_player": index == 1
            ]
        }
        let object: [String: Any] = [
            "selected_day": [
                "played_on": "2026-08-16",
                "label": "2026-08-16 比赛日",
                "match_count": 3,
                "player_entry_count": 12,
                "match_ids": ["m1", "m2", "m3"],
                "scenario_published": true
            ],
            "matches": [[
                "match_id": "m1",
                "stage": "regular_season",
                "stage_label": "常规积分赛",
                "game_no": 1
            ]],
            "predictions": predictions
        ]
        let payload = try JSONDecoder().decode(
            PredictionsResponse.self,
            from: JSONSerialization.data(withJSONObject: object)
        )
        XCTAssertEqual(payload.selectedDay?.playerEntryCount, 12)
        XCTAssertEqual(payload.selectedDay?.matchIDs, ["m1", "m2", "m3"])
        XCTAssertEqual(payload.matches?.first?.displayStage, "常规积分赛")
        XCTAssertEqual(payload.predictions.first?.isStarPlayer, true)
        XCTAssertTrue(payload.isPredictionShareReady)

        var incomplete = object
        incomplete["predictions"] = Array(predictions.dropLast())
        let incompletePayload = try JSONDecoder().decode(
            PredictionsResponse.self,
            from: JSONSerialization.data(withJSONObject: incomplete)
        )
        XCTAssertFalse(incompletePayload.isPredictionShareReady)
    }

    func testStageLabelsPreferServerCopyAndFallbackToLegacyStage() throws {
        let labeled = try JSONDecoder().decode(
            MatchDetail.self,
            from: Data(#"{"match_id":"m1","stage":"regular_season","stage_label":"S组常规赛"}"#.utf8)
        )
        XCTAssertEqual(labeled.displayStage, "S组常规赛")

        let legacy = try JSONDecoder().decode(
            ScheduleMatch.self,
            from: Data(#"{"match_id":"m2","stage":"定级赛"}"#.utf8)
        )
        XCTAssertEqual(legacy.displayStage, "定级赛")
    }

    func testPaginationFixtureDecodes() throws {
        let json = #"{"players":[{"rank":31,"player_id":"p31","display_name":"三十一号","points_total":12.5}],"pagination":{"offset":30,"limit":30,"total":61,"has_more":true}}"#
        let payload = try JSONDecoder().decode(PlayersResponse.self, from: Data(json.utf8))
        XCTAssertEqual(payload.players.first?.playerID, "p31")
        XCTAssertEqual(payload.pagination?.offset, 30)
        XCTAssertEqual(payload.pagination?.limit, 30)
        XCTAssertEqual(payload.pagination?.total, 61)
        XCTAssertEqual(payload.pagination?.hasMore, true)
    }

    func testDimensionHistoryAcceptsStringAndNumericIntegers() throws {
        let json = #"[{"played_on":"2026-08-01","seat":"9","games_played":"3","wins":"2","daily_points":"10.5"},{"played_on":"2026-08-02","seat":4,"games_played":3,"wins":1,"daily_points":5}]"#
        let rows = try JSONDecoder().decode([DimensionHistory].self, from: Data(json.utf8))
        XCTAssertEqual(rows[0].seat, 9)
        XCTAssertEqual(rows[0].gamesPlayed, 3)
        XCTAssertEqual(rows[0].wins, 2)
        XCTAssertEqual(rows[1].seat, 4)
        XCTAssertEqual(rows[1].dailyPoints?.text, "5")
    }

    @MainActor
    func testEverySupportedUniversalLinkRoute() throws {
        let suite = "DeepLinkMatrix.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let app = AppState(api: APIClient(), defaults: defaults)
        let cases: [(String, AppTab, AppRoute?)] = [
            ("/players/p1", .players, .player("p1")),
            ("/teams/t1", .home, .team("t1")),
            ("/matches/m1", .home, .match("m1")),
            ("/days/2026-08-03", .home, .day("2026-08-03")),
            ("/guilds/g1", .guilds, .guild("g1")),
            ("/guilds", .guilds, nil),
            ("/competitions", .competitions, nil),
        ]

        for (path, tab, route) in cases {
            let url = try XCTUnwrap(URL(string: "https://wolf.metauniverse-cn.xyz\(path)"))
            XCTAssertTrue(app.handleDeepLink(url), "未识别 \(path)")
            XCTAssertEqual(app.selectedTab, tab)
            XCTAssertEqual(app.tabRouter.router(for: tab).path, route.map { [$0] } ?? [])
        }
        XCTAssertFalse(app.handleDeepLink(URL(string: "https://example.com/players/p1")!))
    }
}
