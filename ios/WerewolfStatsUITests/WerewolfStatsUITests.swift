import XCTest

@MainActor
final class WerewolfStatsUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testFourPrimaryTabsAreVisible() {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["首页"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.tabBars.buttons["赛事"].exists)
        XCTAssertTrue(app.tabBars.buttons["门派"].exists)
        XCTAssertTrue(app.tabBars.buttons["选手"].exists)
    }

    func testFirstLaunchCanOpenCompetitionPicker() {
        let app = XCUIApplication()
        app.launchArguments += ["-resetUserDefaults", "YES"]
        app.launch()
        app.tabBars.buttons["赛事"].tap()
        XCTAssertTrue(app.navigationBars["赛事"].waitForExistence(timeout: 8))
    }

    func testFirstLaunchSelectsCompetitionAndLoadsDashboard() {
        _ = launchWithSelectedCompetition()
    }

    func testSearchPredictionAndComparisonEntryPoints() {
        let app = launchWithSelectedCompetition()

        let search = app.searchFields.firstMatch
        if !search.waitForExistence(timeout: 3) {
            app.swipeDown()
        }
        XCTAssertTrue(search.waitForExistence(timeout: 5))
        search.tap()
        search.typeText("绝不存在的选手XYZ")
        XCTAssertTrue(app.staticTexts["当前赛事没有匹配结果。"].waitForExistence(timeout: 15))

        let closeSearch = app.buttons["Close"]
        XCTAssertTrue(closeSearch.waitForExistence(timeout: 5))
        closeSearch.tap()

        XCTAssertTrue(app.buttons["home-predictions"].waitForExistence(timeout: 8))
        app.buttons["home-predictions"].tap()
        XCTAssertTrue(app.navigationBars["当天三局胜率预测"].waitForExistence(timeout: 15))
        app.navigationBars["当天三局胜率预测"].buttons.firstMatch.tap()

        app.buttons["home-compare"].tap()
        XCTAssertTrue(app.navigationBars["选手对比"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["交换对比对象"].waitForExistence(timeout: 20))
    }

    func testPlayerDetailFollowAndMiniProgramShareCard() {
        let app = launchWithSelectedCompetition()
        app.tabBars.buttons["选手"].tap()

        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "player-row-"))
        let firstPlayer = rows.firstMatch
        XCTAssertTrue(firstPlayer.waitForExistence(timeout: 20))
        firstPlayer.tap()

        let follow = app.buttons["关注"]
        XCTAssertTrue(follow.waitForExistence(timeout: 15))
        follow.tap()
        XCTAssertTrue(app.buttons["取消关注"].waitForExistence(timeout: 5))

        let card = app.buttons["战绩卡"].firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 20))
        card.tap()
        XCTAssertTrue(app.navigationBars["战绩卡"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["share-card-preview"].waitForExistence(timeout: 25))

        XCTAssertTrue(app.descendants(matching: .any)["share-qr-mini-program-note"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["微信小程序"].exists)
        XCTAssertFalse(app.buttons["App / 网页"].exists)
    }

    func testPlayerListLoadsNextPage() {
        let app = launchWithSelectedCompetition()
        app.tabBars.buttons["选手"].tap()

        let list = app.descendants(matching: .any)["players-list"]
        XCTAssertTrue(list.waitForExistence(timeout: 20))
        let initialValue = String(describing: list.value ?? "")
        XCTAssertTrue(initialValue.hasPrefix("已加载 "))

        for _ in 0..<18 {
            list.swipeUp()
            if String(describing: list.value ?? "") != initialValue { break }
        }
        XCTAssertNotEqual(String(describing: list.value ?? ""), initialValue)
    }

    func testNetworkErrorShowsRetry() {
        let app = XCUIApplication()
        app.launchArguments += ["-resetUserDefaults", "YES", "-APIBaseURL", "http://127.0.0.1:9"]
        app.launch()
        app.tabBars.buttons["赛事"].tap()

        let retry = app.buttons["重试"]
        XCTAssertTrue(retry.waitForExistence(timeout: 20))
        retry.tap()
        XCTAssertTrue(retry.waitForExistence(timeout: 20))
    }

    func testCompetitionsAreGroupedByCity() throws {
        let server = try LoopbackHTTPFixtureServer(responses: LeaderboardUITestFixture.responses())
        addTeardownBlock { server.stop() }
        let app = XCUIApplication()
        app.launchArguments += ["-resetUserDefaults", "YES", "-APIBaseURL", server.baseURL.absoluteString]
        app.launch()
        app.tabBars.buttons["赛事"].tap()

        let guangzhou = app.buttons["competition-city-广州"]
        let shenzhen = app.buttons["competition-city-深圳"]
        XCTAssertTrue(guangzhou.waitForExistence(timeout: 10))
        XCTAssertTrue(shenzhen.exists)
        XCTAssertEqual(String(describing: guangzhou.value ?? ""), "已展开")
        XCTAssertEqual(String(describing: shenzhen.value ?? ""), "已收起")

        shenzhen.tap()
        XCTAssertEqual(String(describing: shenzhen.value ?? ""), "已展开")
        XCTAssertTrue(app.staticTexts["深圳 UI 测试赛"].waitForExistence(timeout: 5))
    }

    func testPredictionSharePosterMatchesMiniProgramEntry() throws {
        let server = try LoopbackHTTPFixtureServer(responses: PredictionUITestFixture.responses())
        addTeardownBlock { server.stop() }
        let app = launchWithSelectedCompetition(apiBaseURL: server.baseURL)

        app.buttons["home-predictions"].tap()
        XCTAssertTrue(app.navigationBars["当天三局胜率预测"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["prediction-day-2026-08-17"].waitForExistence(timeout: 10))
        let share = app.buttons["prediction-share-card"]
        XCTAssertTrue(share.waitForExistence(timeout: 10))
        share.tap()

        XCTAssertTrue(app.navigationBars["当天预测分享图"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["prediction-share-preview"].waitForExistence(timeout: 25))
    }

    func testLeaderboardMatchesMiniProgramSectionsAndFullServerOrder() throws {
        let server = try LoopbackHTTPFixtureServer(responses: LeaderboardUITestFixture.responses())
        addTeardownBlock { server.stop() }
        let app = launchWithSelectedCompetition(apiBaseURL: server.baseURL)

        let homeScrollView = app.scrollViews.firstMatch
        XCTAssertTrue(homeScrollView.waitForExistence(timeout: 5))
        let regularSeasonStage = app.buttons["leaderboard-stage-regular_season"]
        scrollToElement(regularSeasonStage, in: homeScrollView)
        XCTAssertTrue(regularSeasonStage.isHittable)
        regularSeasonStage.tap()

        let leaderboard = app.descendants(matching: .any)["leaderboard-list"]
        XCTAssertTrue(leaderboard.waitForExistence(timeout: 10))

        let sSection = app.buttons["leaderboard-section-S"]
        let fSection = app.buttons["leaderboard-section-F"]
        XCTAssertTrue(sSection.waitForExistence(timeout: 5))
        XCTAssertTrue(fSection.exists)

        let firstSRow = app.buttons["leaderboard-row-teams-s-team-1"]
        let secondSRow = app.buttons["leaderboard-row-teams-s-team-2"]
        XCTAssertTrue(firstSRow.waitForExistence(timeout: 5))
        XCTAssertTrue(secondSRow.waitForExistence(timeout: 5))
        XCTAssertTrue(firstSRow.label.contains("S服序第一队"))
        XCTAssertTrue(firstSRow.label.contains("直通"))
        XCTAssertLessThan(firstSRow.frame.minY, secondSRow.frame.minY, "分组榜必须保留服务端顺序，不能按积分在客户端重排")
        XCTAssertFalse(app.staticTexts["不应显示的聚合队"].exists)
        recordScreenshot(app, name: "排行榜-S组")

        fSection.tap()
        let firstFRow = app.buttons["leaderboard-row-teams-f-team-1"]
        XCTAssertTrue(firstFRow.waitForExistence(timeout: 5))
        XCTAssertTrue(firstFRow.label.contains("F服序第一队"))
        XCTAssertTrue(firstFRow.label.contains("直通"))

        let playersBoard = app.buttons["leaderboard-board-players"]
        scrollToElement(playersBoard, in: homeScrollView)
        playersBoard.tap()
        XCTAssertFalse(app.buttons["leaderboard-section-S"].waitForExistence(timeout: 1))
        XCTAssertFalse(app.buttons["leaderboard-section-F"].exists)
        XCTAssertTrue(app.buttons["leaderboard-row-players-regular-player"].waitForExistence(timeout: 5))

        let mvpBoard = app.buttons["leaderboard-board-mvp"]
        mvpBoard.tap()
        XCTAssertTrue(app.buttons["leaderboard-row-mvp-regular-mvp"].waitForExistence(timeout: 5))
        let svpBoard = app.buttons["leaderboard-board-svp"]
        svpBoard.tap()
        XCTAssertTrue(app.buttons["leaderboard-row-svp-regular-svp"].waitForExistence(timeout: 5))

        app.buttons["leaderboard-board-teams"].tap()
        XCTAssertTrue(app.buttons["leaderboard-section-F"].waitForExistence(timeout: 5))
        let lastFRow = app.buttons["leaderboard-row-teams-f-team-23"]
        scrollToElement(lastFRow, in: homeScrollView, maximumSwipes: 30)
        XCTAssertTrue(lastFRow.exists, "分组榜必须展示服务端返回的全部 23 行，不能只保留前 20 行")
        recordScreenshot(app, name: "排行榜-F组-第23名")
    }

    private func launchWithSelectedCompetition(apiBaseURL: URL? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments += ["-resetUserDefaults", "YES"]
        if let apiBaseURL {
            app.launchArguments += ["-APIBaseURL", apiBaseURL.absoluteString]
        }
        app.launch()
        app.tabBars.buttons["赛事"].tap()

        let selectSeason = app.buttons["进入该赛季"].firstMatch
        XCTAssertTrue(selectSeason.waitForExistence(timeout: 15))
        selectSeason.tap()

        XCTAssertTrue(app.navigationBars["一颗小草赛事"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["当前赛事"].waitForExistence(timeout: 20))
        return app
    }

    private func scrollToElement(_ element: XCUIElement, in scrollContainer: XCUIElement, maximumSwipes: Int = 12) {
        for _ in 0..<maximumSwipes where !element.exists || !element.isHittable {
            if element.exists, element.frame.midY < scrollContainer.frame.minY {
                scrollContainer.swipeDown()
            } else {
                scrollContainer.swipeUp()
            }
        }
    }

    private func recordScreenshot(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
