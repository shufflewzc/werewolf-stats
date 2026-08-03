import XCTest
@testable import WerewolfStats

final class DashboardLeaderboardTests: XCTestCase {
    func testCanonicalSectionsDecodeArbitraryGroupsAndPreserveServerOrder() throws {
        let payload = try decodeDashboard(
            #"""
            {
              "team_leaderboard_sections": {
                "regular_season": [
                  {
                    "key": "S",
                    "label": "S组",
                    "title": "S组常规赛榜",
                    "rows": [
                      {"rank": 7, "team_id": "s-low", "short_name": "低分先返回", "points_total": "3.00"},
                      {"rank": 2, "team_id": "s-high", "short_name": "高分后返回", "points_total": "99.00"}
                    ]
                  },
                  {
                    "key": "F",
                    "label": "F组",
                    "title": "F组常规赛榜",
                    "rows": [
                      {"rank": 1, "team_id": "f-1", "short_name": "F队", "points_total": 21.5}
                    ]
                  },
                  {
                    "key": "ELITE",
                    "label": "精英组",
                    "title": "精英组常规赛榜",
                    "rows": [
                      {
                        "rank": 1,
                        "team_id": "elite-1",
                        "short_name": "精英队",
                        "points_total": 30,
                        "badges": [{"text": "直通", "style": "orange", "kind": "progress"}]
                      }
                    ]
                  }
                ]
              }
            }
            """#
        )

        let sections = payload.teamSections(for: "regular_season")
        XCTAssertEqual(sections.map(\.key), ["S", "F", "ELITE"])
        XCTAssertEqual(sections.map(\.title), ["S组常规赛榜", "F组常规赛榜", "精英组常规赛榜"])
        XCTAssertEqual(sections[0].rows.map(\.teamID), ["s-low", "s-high"], "客户端必须保留服务端行顺序")
        XCTAssertEqual(sections[0].rows.map(\.pointsTotal?.text), ["3.00", "99.00"])
        XCTAssertEqual(sections[2].rows.first?.badges, [LeaderboardBadge(text: "直通", style: "orange", kind: "progress")])
    }

    func testAllAndRegularSeasonSelectionAcrossAllFourBoards() throws {
        let payload = try decodeDashboard(
            #"""
            {
              "leaderboards": {
                "teams": [{"rank": 1, "team_id": "all-team", "short_name": "全部战队"}],
                "players": [{"rank": 1, "player_id": "all-player", "display_name": "全部选手"}],
                "mvp": [{"rank": 1, "player_id": "all-mvp", "display_name": "全部MVP"}],
                "svp": [{"rank": 1, "player_id": "all-svp", "display_name": "全部SVP"}]
              },
              "leaderboards_by_stage": {
                "regular_season": {
                  "teams": [{"rank": 1, "team_id": "regular-aggregate", "short_name": "常规赛聚合"}],
                  "players": [{"rank": 1, "player_id": "regular-player", "display_name": "常规赛选手"}],
                  "mvp": [{"rank": 1, "player_id": "regular-mvp", "display_name": "常规赛MVP"}],
                  "svp": [{"rank": 1, "player_id": "regular-svp", "display_name": "常规赛SVP"}]
                }
              },
              "team_leaderboard_sections": {
                "regular_season": [
                  {"key": "S", "label": "S组", "title": "S组常规赛榜", "rows": [{"rank": 1, "team_id": "regular-s", "short_name": "S队"}]},
                  {"key": "F", "label": "F组", "title": "F组常规赛榜", "rows": [{"rank": 1, "team_id": "regular-f", "short_name": "F队"}]}
                ]
              }
            }
            """#
        )

        let cases: [(selection: LeaderboardSelection, expectedID: String)] = [
            (.init(board: .teams, stageKey: "all", teamSectionKey: "F"), "all-team"),
            (.init(board: .players, stageKey: "all"), "all-player"),
            (.init(board: .mvp, stageKey: "all"), "all-mvp"),
            (.init(board: .svp, stageKey: "all"), "all-svp"),
            (.init(board: .teams, stageKey: "regular_season", teamSectionKey: "S"), "regular-s"),
            (.init(board: .teams, stageKey: "regular_season", teamSectionKey: "F"), "regular-f"),
            (.init(board: .players, stageKey: "regular_season", teamSectionKey: "S"), "regular-player"),
            (.init(board: .mvp, stageKey: "regular_season", teamSectionKey: "S"), "regular-mvp"),
            (.init(board: .svp, stageKey: "regular_season", teamSectionKey: "S"), "regular-svp"),
        ]

        for item in cases {
            let row = try XCTUnwrap(payload.leaderboardRows(for: item.selection).first)
            XCTAssertEqual(row.teamID ?? row.playerID, item.expectedID, "选择 \(item.selection.stageKey)/\(item.selection.board.rawValue) 错误")
        }
    }

    func testSelectionNormalizationAndTeamSectionPreservationAcrossBoardChanges() throws {
        let payload = try decodeDashboard(
            #"""
            {
              "leaderboard_stages": [
                {"key": "all", "label": "全部"},
                {"key": "placement", "label": "定级赛"},
                {"key": "regular_season", "label": "常规赛"}
              ],
              "team_leaderboard_sections": {
                "regular_season": [
                  {"key": "S", "label": "S组", "title": "S组常规赛榜", "rows": []},
                  {"key": "F", "label": "F组", "title": "F组常规赛榜", "rows": []}
                ]
              }
            }
            """#
        )

        var invalidStage = LeaderboardSelection(board: .teams, stageKey: "removed_stage", teamSectionKey: "F")
        invalidStage.normalize(for: payload)
        XCTAssertEqual(invalidStage.stageKey, "all")
        XCTAssertEqual(invalidStage.teamSectionKey, "")

        var selection = LeaderboardSelection(board: .teams, stageKey: "regular_season", teamSectionKey: "removed_group")
        selection.normalize(for: payload)
        XCTAssertEqual(selection.teamSectionKey, "S", "无效组别应回退到服务端第一个组")

        selection.selectTeamSection("F", in: payload)
        selection.selectBoard(.players)
        XCTAssertEqual(selection.teamSectionKey, "F", "切到个人榜时应保留当前战队分组")
        selection.selectBoard(.mvp)
        selection.selectBoard(.teams)
        XCTAssertEqual(selection.teamSectionKey, "F", "返回战队榜时应恢复原分组")

        selection.selectTeamSection("not-present", in: payload)
        XCTAssertEqual(selection.teamSectionKey, "F", "无效的直接分组选择应被忽略")

        selection.selectStage("placement", in: payload)
        XCTAssertEqual(selection.stageKey, "placement")
        XCTAssertEqual(selection.teamSectionKey, "")
        selection.selectStage("regular_season", in: payload)
        XCTAssertEqual(selection.teamSectionKey, "S")
    }

    func testLegacySectionsUseSFFirstThenNaturalOrder() throws {
        let payload = try decodeDashboard(
            #"""
            {
              "regular_season_team_leaderboards": {
                "Z10": [{"rank": 1, "team_id": "z10"}],
                "F": [{"rank": 1, "team_id": "f"}],
                "A": [{"rank": 1, "team_id": "a"}],
                "Z2": [{"rank": 1, "team_id": "z2"}],
                "S": [{"rank": 1, "team_id": "s"}]
              }
            }
            """#
        )

        let sections = payload.teamSections(for: "regular_season")
        XCTAssertEqual(sections.map(\.key), ["S", "F", "A", "Z2", "Z10"])
        XCTAssertEqual(sections.map(\.label), ["S组", "F组", "A组", "Z2组", "Z10组"])
        XCTAssertEqual(sections.map(\.title), ["S组常规赛榜", "F组常规赛榜", "A组常规赛榜", "Z2组常规赛榜", "Z10组常规赛榜"])
        XCTAssertEqual(sections.map { $0.rows.first?.teamID }, ["s", "f", "a", "z2", "z10"])
    }

    func testCanonicalEmptySectionsSuppressLegacyAndUseStageAggregate() throws {
        let payload = try decodeDashboard(
            #"""
            {
              "leaderboards_by_stage": {
                "regular_season": {
                  "teams": [{"rank": 1, "team_id": "aggregate", "short_name": "聚合榜"}]
                }
              },
              "team_leaderboard_sections": {"regular_season": []},
              "regular_season_team_leaderboards": {
                "S": [{"rank": 1, "team_id": "legacy-s", "short_name": "旧S榜"}]
              }
            }
            """#
        )

        XCTAssertEqual(payload.teamSections(for: "regular_season"), [])
        let selection = LeaderboardSelection(board: .teams, stageKey: "regular_season", teamSectionKey: "S")
        XCTAssertEqual(payload.leaderboardRows(for: selection).map(\.teamID), ["aggregate"])
    }

    func testBadgeNilEmptyAndServerProvidedStatesRemainDistinct() throws {
        let rows = try JSONDecoder().decode(
            [LeaderboardRow].self,
            from: Data(
                #"""
                [
                  {
                    "rank": 1,
                    "team_id": "fallback",
                    "regular_season_group": "S",
                    "progress_status": "晋级"
                  },
                  {
                    "rank": 2,
                    "team_id": "explicit-empty",
                    "regular_season_group": "S",
                    "progress_status": "晋级",
                    "badges": []
                  },
                  {
                    "rank": 3,
                    "team_id": "server",
                    "regular_season_group": "S",
                    "progress_status": "晋级",
                    "badges": [
                      {"text": "服务端第一", "style": "red", "kind": "custom"},
                      {"text": "服务端第二", "style": "gold", "kind": "group"}
                    ]
                  }
                ]
                """#.utf8
            )
        )

        XCTAssertNil(rows[0].badges)
        XCTAssertEqual(
            LeaderboardDisplayRow(row: rows[0], board: .teams).badges,
            [
                LeaderboardBadge(text: "S", style: "gold", kind: "group"),
                LeaderboardBadge(text: "晋级", style: "green", kind: "progress"),
            ]
        )

        XCTAssertEqual(rows[1].badges, [])
        XCTAssertEqual(LeaderboardDisplayRow(row: rows[1], board: .teams).badges, [])

        XCTAssertEqual(
            LeaderboardDisplayRow(row: rows[2], board: .teams).badges,
            [
                LeaderboardBadge(text: "服务端第一", style: "red", kind: "custom"),
                LeaderboardBadge(text: "服务端第二", style: "gold", kind: "group"),
            ],
            "服务端徽章应原样保留顺序和样式，不能混入旧字段回退徽章"
        )
    }

    func testBoardTitlesMetadataAwardDatesAndStableIDs() throws {
        XCTAssertEqual(LeaderboardBoard.allCases.map(\.title), ["战队积分", "个人积分", "个人MVP", "个人SVP"])

        let rows = try JSONDecoder().decode(
            [LeaderboardRow].self,
            from: Data(
                #"""
                [
                  {"rank": 1, "team_id": "t1", "short_name": "狼咖", "points_total": "34.00", "win_rate": "66.7%", "matches_represented": 9},
                  {"rank": 2, "player_id": "p1", "display_name": "小鱼", "team_name": "洵岛", "points_total": 41.5, "games_played": 12, "is_star_player": true},
                  {"rank": 1, "player_id": "p1", "display_name": "小鱼", "team_name": "洵岛", "award_count": 3, "award_label": "MVP", "latest_awarded_on": "2026-08-01"},
                  {"rank": 1, "player_id": "p2", "display_name": "阿北", "team_name": "狼咖", "award_count": 2, "award_label": "SVP", "latest_awarded_on": "2026-07-31"}
                ]
                """#.utf8
            )
        )

        let team = LeaderboardDisplayRow(row: rows[0], board: .teams)
        XCTAssertEqual(team.id, "teams:t1")
        XCTAssertEqual(team.title, "狼咖")
        XCTAssertEqual(team.metadata, "胜率 66.7% · 出赛 9 场")
        XCTAssertEqual(team.valueText, "34.00")
        XCTAssertEqual(team.valueLabel, "积分")

        let player = LeaderboardDisplayRow(row: rows[1], board: .players)
        XCTAssertEqual(player.id, "players:p1")
        XCTAssertEqual(player.metadata, "洵岛 · 出场 12 局")
        XCTAssertEqual(player.valueText, "41.50")
        XCTAssertEqual(player.valueLabel, "积分")
        XCTAssertTrue(player.isStarPlayer)

        let mvp = LeaderboardDisplayRow(row: rows[2], board: .mvp)
        XCTAssertEqual(mvp.id, "mvp:p1")
        XCTAssertEqual(mvp.metadata, "洵岛 · 最近 2026-08-01")
        XCTAssertEqual(mvp.valueText, "3")
        XCTAssertEqual(mvp.valueLabel, "MVP")

        let svp = LeaderboardDisplayRow(row: rows[3], board: .svp)
        XCTAssertEqual(svp.id, "svp:p2")
        XCTAssertEqual(svp.metadata, "狼咖 · 最近 2026-07-31")
        XCTAssertEqual(svp.valueText, "2")
        XCTAssertEqual(svp.valueLabel, "SVP")
        XCTAssertNotEqual(mvp.id, LeaderboardDisplayRow(row: rows[2], board: .players).id)
    }

    func testLeaderboardIntegerFieldsAcceptNumbersAndNumericStrings() throws {
        let rows = try JSONDecoder().decode(
            [LeaderboardRow].self,
            from: Data(
                #"""
                [
                  {"rank":"1","team_id":"team","matches_represented":"12.0"},
                  {"rank":2,"player_id":"player","games_played":"9","award_count":"3"}
                ]
                """#.utf8
            )
        )

        XCTAssertEqual(rows[0].rank, 1)
        XCTAssertEqual(rows[0].matchesRepresented, 12)
        XCTAssertEqual(rows[1].rank, 2)
        XCTAssertEqual(rows[1].gamesPlayed, 9)
        XCTAssertEqual(rows[1].awardCount, 3)
    }

    func testLeaderboardReturnsEveryRowBeyondTwentyWithoutSortingOrTruncation() throws {
        let rowsJSON = (1...25).map { index in
            #"{"rank":\#(index),"player_id":"p\#(index)","display_name":"选手\#(index)","points_total":\#(26 - index)}"#
        }.joined(separator: ",")
        let payload = try decodeDashboard(
            #"{"leaderboards":{"players":[\#(rowsJSON)]}}"#
        )
        let selection = LeaderboardSelection(board: .players, stageKey: "all")

        let rows = payload.leaderboardRows(for: selection)
        XCTAssertEqual(rows.count, 25)
        XCTAssertEqual(rows.map(\.playerID), (1...25).map { "p\($0)" })
        XCTAssertEqual(rows.last?.pointsTotal?.text, "1", "必须保留服务端顺序，不能在客户端按积分重排")

        let displayRows = rows.map { LeaderboardDisplayRow(row: $0, board: selection.board) }
        XCTAssertEqual(displayRows.count, 25)
        XCTAssertEqual(displayRows.last?.id, "players:p25")
    }

    private func decodeDashboard(_ json: String) throws -> DashboardResponse {
        try JSONDecoder().decode(DashboardResponse.self, from: Data(json.utf8))
    }
}
