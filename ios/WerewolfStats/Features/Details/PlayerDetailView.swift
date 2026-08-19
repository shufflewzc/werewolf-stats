import SwiftUI

struct PlayerDetailView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let playerID: String
    @State private var state: LoadState<PlayerDetailResponse> = .idle

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else {
                switch state {
                case .idle, .loading: LoadingContent(label: "正在读取选手详情")
                case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
                case .loaded(let payload, let stale): content(payload, stale: stale)
                }
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button(app.isFavorite(playerID) ? "取消关注" : "关注", systemImage: app.isFavorite(playerID) ? "star.fill" : "star") { app.toggleFavorite(playerID) }
                Button("分享战绩卡", systemImage: "square.and.arrow.up") { router.navigate(to: .share(playerID: playerID)) }
            }
        }
        .task(id: app.selectedScope) { await load() }
    }

    private var title: String {
        if case .loaded(let payload, _) = state { return payload.player.name }
        return "选手详情"
    }

    private func content(_ payload: PlayerDetailResponse, stale: Bool) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                if stale { StaleBanner() }
                playerHero(payload.player)
                HStack {
                    Button("胜率预测") { router.navigate(to: .predictions(playedOn: nil, matchID: nil)) }.buttonStyle(.bordered)
                    Button("选手对比") { router.navigate(to: .compare(kind: .player, leftID: playerID)) }.buttonStyle(.bordered)
                    Button("战绩卡") { router.navigate(to: .share(playerID: playerID)) }.buttonStyle(.borderedProminent)
                }.font(.caption).frame(maxWidth: .infinity)
                if let metrics = payload.metrics { MetricGrid(metrics: Array(metrics.prefix(6))) }
                if let achievements = payload.achievements, !achievements.isEmpty { achievementsSection(achievements) }
                if let insights = payload.insights { insightSection(insights) }
                if let dimension = payload.dimension { dimensionSection(dimension) }
                if let roles = payload.roles, !roles.isEmpty { roleSection(roles) }
                if let matches = payload.recentMatches, !matches.isEmpty { recentSection(matches) }
            }.padding()
        }.refreshable { await load(force: true) }.pageBackground()
    }

    private func playerHero(_ player: PlayerDetail) -> some View {
        HStack(spacing: 18) {
            RemoteImage(url: app.api.assetURL(player.photo), size: 90)
            VStack(alignment: .leading, spacing: 7) {
                Text(player.teamName ?? "未绑定战队").font(.caption).foregroundStyle(.white.opacity(0.72))
                HStack { Text(player.name).font(.largeTitle.bold()); if player.isStarPlayer == true { Image(systemName: "star.fill").foregroundStyle(Brand.gold) } }
                Text("排名 #\(player.rank.map(String.init) ?? "–") · \(player.owner ?? "未绑定账号")").font(.caption).foregroundStyle(.white.opacity(0.75))
                PowerBadge(rating: player.powerRating)
            }.foregroundStyle(.white)
            Spacer()
        }
        .padding(20).background(LinearGradient(colors: [Brand.navy, Brand.blue], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 22))
    }

    private func achievementsSection(_ achievements: [Achievement]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "成就标签", note: "\(achievements.count) 个")
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(achievements) { item in
                    VStack(alignment: .leading, spacing: 4) { Text(item.code).font(.caption.bold()).foregroundStyle(Brand.gold); Text(item.title).font(.headline); Text(item.meta ?? item.description ?? "").font(.caption2).foregroundStyle(.secondary).lineLimit(2) }
                        .frame(maxWidth: .infinity, minHeight: 86, alignment: .topLeading).padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                }
            }
        }
    }

    private func insightSection(_ insights: PlayerInsights) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeading(title: "胜率画像")
            insightRow("综合胜率", insights.overallWinRate)
            insightRow("好人胜率", insights.villagersWinRate)
            insightRow("狼人胜率", insights.werewolvesWinRate)
        }.padding(16).background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
    }

    private func insightRow(_ label: String, _ value: String?) -> some View {
        let number = Double((value ?? "0").replacingOccurrences(of: "%", with: "")) ?? 0
        return VStack(spacing: 5) { HStack { Text(label); Spacer(); Text(value ?? "--").bold() }; ProgressView(value: min(max(number / 100, 0), 1)).tint(Brand.gold) }
    }

    @ViewBuilder private func dimensionSection(_ dimension: PlayerDimension) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeading(title: "维度数据", note: dimension.selectedSeason)
            if dimension.available == true {
                if let metrics = dimension.summaryCards { MetricGrid(metrics: metrics) }
                ForEach(dimension.radar ?? []) { item in
                    VStack(spacing: 5) { HStack { Text(item.label); Spacer(); Text(item.display ?? "--").bold() }; ProgressView(value: min(max(item.ratio ?? 0, 0), 1)).tint(Brand.gold) }
                }
            } else {
                Text(dimension.reason ?? "当前赛事暂无该选手的维度数据。").font(.subheadline).foregroundStyle(.secondary).padding()
            }
        }
    }

    private func roleSection(_ roles: [RoleStat]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeading(title: "角色分布")
            ForEach(roles) { role in VStack(spacing: 5) { HStack { Text(role.role); Spacer(); Text("\(role.games ?? 0) 局 · \(role.share ?? "--")") }; ProgressView(value: min(max((role.width ?? 0) / 100, 0), 1)).tint(Brand.blue) } }
        }.padding(16).background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
    }

    private func recentSection(_ matches: [RecentMatch]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "最近比赛")
            ForEach(matches) { match in
                Button { router.navigate(to: .match(match.matchID)) } label: {
                    HStack { VStack(alignment: .leading) { Text("\(match.playedOn ?? "") · 第\(match.round ?? 0)轮第\(match.gameNo ?? 0)局").font(.headline); Text("\(match.displayStage) · \(match.role ?? "未知角色") · \(match.resultLabel ?? "--")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(match.pointsEarned?.text ?? "--").font(.headline); Image(systemName: "chevron.right") }
                        .padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                }.buttonStyle(.plain)
            }
        }
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }
        state = .loading
        do {
            let result = try await app.api.get("/api/players/\(playerID)", queryItems: scope.queryItems + [URLQueryItem(name: "strict_player_id", value: "1")], as: PlayerDetailResponse.self, forceRefresh: force)
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError { return }
        catch { state = .failed(error.localizedDescription) }
    }
}
