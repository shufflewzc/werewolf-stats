import SwiftUI

struct HomeView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    @State private var state: LoadState<DashboardResponse> = .idle
    @State private var searchQuery = ""
    @State private var searchResults: [SearchResult] = []
    @State private var searchError: String?
    @State private var leaderboardSelection = LeaderboardSelection()

    var body: some View {
        Group {
            if app.selectedScope == nil {
                ScopeRequiredView()
            } else {
                switch state {
                case .idle, .loading: LoadingContent()
                case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
                case .loaded(let payload, let isStale): content(payload, isStale: isStale)
                }
            }
        }
        .navigationTitle("一颗小草赛事")
        .toolbar {
            if app.selectedScope != nil {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("预测", systemImage: "chart.line.uptrend.xyaxis") { router.navigate(to: .predictions(playedOn: nil, matchID: nil)) }
                        .accessibilityIdentifier("home-predictions")
                    Button("对比", systemImage: "arrow.left.arrow.right") { router.navigate(to: .compare(kind: .player, leftID: nil)) }
                        .accessibilityIdentifier("home-compare")
                }
            }
        }
        .task(id: app.selectedScope) { await load() }
        .task(id: searchQuery) { await search() }
    }

    private func content(_ payload: DashboardResponse, isStale: Bool) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                if isStale { StaleBanner() }
                BrandHero(
                    eyebrow: payload.generatedAt ?? "实时赛事数据",
                    title: app.selectedScope?.competition ?? "赛事数据中心",
                    copy: app.selectedScope?.subtitle ?? payload.hero?.featuredLabel ?? ""
                )
                scopeCard
                if let days = payload.matchDays, let latest = days.first { latestDay(latest) }
                if let metrics = payload.metrics, !metrics.isEmpty { MetricGrid(metrics: Array(metrics.prefix(4))) }
                searchSection
                HomeLeaderboardView(payload: payload, selection: $leaderboardSelection) { row in
                    openLeaderboardRow(row)
                }
                topPlayers(payload.topPlayers ?? [])
                topTeams(payload.topTeams ?? [])
                matchDays(payload.matchDays ?? [])
                schedule(payload.scheduleMatches ?? [])
            }
            .padding()
        }
        .refreshable { await load(force: true) }
        .pageBackground()
        .searchable(text: $searchQuery, prompt: "搜索选手、战队或门派")
    }

    private var scopeCard: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("当前赛事").font(.caption).foregroundStyle(.secondary)
                Text(app.selectedScope?.competition ?? "").font(.headline)
                Text(app.selectedScope?.subtitle ?? "").font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button("切换") { app.selectedTab = .competitions }.buttonStyle(.bordered)
        }
        .padding(16).background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
    }

    private func latestDay(_ day: MatchDaySummary) -> some View {
        Button { router.navigate(to: .day(day.playedOn)) } label: {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Text("最近比赛日").font(.caption).foregroundStyle(.secondary)
                    Text(day.playedOn).font(.title2.bold())
                    Text("\(day.matchCount) 场 · 点击查看当日榜单").font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer(); Image(systemName: "chevron.right")
            }
            .padding(16).background(Brand.paleGold.opacity(0.45), in: RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder private var searchSection: some View {
        if !searchQuery.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "搜索结果", note: searchResults.isEmpty ? nil : "\(searchResults.count) 项")
                if let searchError { Text(searchError).font(.caption).foregroundStyle(.red) }
                ForEach(searchResults) { result in
                    Button { open(result) } label: {
                        HStack {
                            Text(result.typeLabel ?? result.type).font(.caption.bold()).foregroundStyle(Brand.gold)
                            VStack(alignment: .leading) {
                                Text(result.title).font(.headline)
                                if let subtitle = result.subtitle { Text(subtitle).font(.caption).foregroundStyle(.secondary) }
                            }
                            Spacer(); Image(systemName: "chevron.right")
                        }
                        .padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                    }.buttonStyle(.plain)
                }
                if searchQuery.count >= 2, searchResults.isEmpty, searchError == nil {
                    Text("当前赛事没有匹配结果。").font(.subheadline).foregroundStyle(.secondary)
                }
            }
        }
    }

    @ViewBuilder private func topPlayers(_ players: [PlayerSummary]) -> some View {
        if !players.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "领先选手")
                ForEach(players.prefix(5)) { player in
                    Button { router.navigate(to: .player(player.playerID)) } label: {
                        HStack { RemoteImage(url: app.api.assetURL(player.photo)); VStack(alignment: .leading) { Text(player.displayName).font(.headline); Text("\(player.teamName ?? "未绑定战队") · 胜率 \(player.winRate ?? "--")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(player.pointsTotal?.text ?? "--").font(.headline) }
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder private func topTeams(_ teams: [TeamSummary]) -> some View {
        if !teams.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "领先战队")
                ForEach(teams.prefix(5)) { team in
                    Button { router.navigate(to: .team(team.teamID)) } label: {
                        HStack { RemoteImage(url: app.api.assetURL(team.logo), circular: false); VStack(alignment: .leading) { Text(team.shortName ?? team.name).font(.headline); Text("胜率 \(team.winRate ?? "--") · \(team.matchesRepresented ?? 0) 场").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(team.pointsTotal?.text ?? "--").font(.headline) }
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder private func matchDays(_ days: [MatchDaySummary]) -> some View {
        if !days.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "最近比赛日")
                ForEach(days) { day in
                    Button { router.navigate(to: .day(day.playedOn)) } label: {
                        HStack { Image(systemName: "calendar"); Text(day.playedOn); Spacer(); Text("\(day.matchCount) 场").foregroundStyle(.secondary); Image(systemName: "chevron.right") }
                            .padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder private func schedule(_ matches: [ScheduleMatch]) -> some View {
        if !matches.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "赛程")
                ForEach(matches) { match in
                    Button { router.navigate(to: .match(match.matchID)) } label: {
                        HStack { VStack(alignment: .leading) { Text(match.playedOn ?? "待定").font(.headline); Text("第\(match.round ?? 0)轮第\(match.gameNo ?? 0)局 · \(match.tableLabel ?? "")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Image(systemName: "chevron.right") }
                            .padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { state = .idle; return }
        if case .loaded = state, !force { } else { state = .loading }
        do {
            let result = try await app.api.get("/api/dashboard", queryItems: scope.queryItems, as: DashboardResponse.self, forceRefresh: force)
            leaderboardSelection.normalize(for: result.value)
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError { return }
        catch { state = .failed(error.localizedDescription) }
    }

    private func search() async {
        searchResults = []; searchError = nil
        guard searchQuery.count >= 2, let scope = app.selectedScope else { return }
        do {
            try await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            let result = try await app.api.get("/api/search", queryItems: scope.queryItems + [URLQueryItem(name: "q", value: searchQuery)], as: SearchResponse.self, forceRefresh: true)
            searchResults = result.value.results
        } catch is CancellationError { return }
        catch { searchError = error.localizedDescription }
    }

    private func open(_ result: SearchResult) {
        switch result.type {
        case "player": router.navigate(to: .player(result.entityID))
        case "team": router.navigate(to: .team(result.entityID))
        case "guild": router.navigate(to: .guild(result.entityID))
        default: break
        }
    }

    private func openLeaderboardRow(_ row: LeaderboardRow) {
        if let id = row.teamID {
            router.navigate(to: .team(id))
        } else if let id = row.playerID {
            router.navigate(to: .player(id))
        }
    }
}
