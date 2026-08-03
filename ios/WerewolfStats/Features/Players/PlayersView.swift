import SwiftUI

struct PlayersView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    @State private var state: LoadState<PlayersResponse> = .idle
    @State private var players: [PlayerSummary] = []
    @State private var pagination: Pagination?
    @State private var loadingMore = false
    @State private var loadMoreError: String?

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else {
                switch state {
                case .idle, .loading: LoadingContent(label: "正在读取选手榜")
                case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
                case .loaded(let payload, let stale): list(payload: payload, stale: stale)
                }
            }
        }
        .navigationTitle("选手")
        .toolbar { if app.selectedScope != nil { Button("选手对比", systemImage: "arrow.left.arrow.right") { router.navigate(to: .compare(kind: .player, leftID: nil)) } } }
        .task(id: app.selectedScope) { await load() }
    }

    private func list(payload: PlayersResponse, stale: Bool) -> some View {
        List {
            if stale { StaleBanner().listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            if let metrics = payload.metrics, !metrics.isEmpty { MetricGrid(metrics: Array(metrics.prefix(4))).listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            Section("当前赛事选手") {
                ForEach(players) { player in
                    Button { router.navigate(to: .player(player.playerID)) } label: {
                        HStack(spacing: 12) {
                            RankBadge(rank: player.rank)
                            RemoteImage(url: app.api.assetURL(player.photo))
                            VStack(alignment: .leading, spacing: 4) {
                                HStack { Text(player.displayName).font(.headline); if player.isStarPlayer == true { Image(systemName: "star.fill").foregroundStyle(Brand.gold) }; PowerBadge(rating: player.powerRating) }
                                Text("\(player.teamName ?? "未绑定战队") · \(player.gamesPlayed ?? 0) 局 · 胜率 \(player.winRate ?? "--")").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer(); Text(player.pointsTotal?.text ?? "--").font(.headline)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("player-row-\(player.playerID)")
                    .onAppear { if player.id == players.last?.id { Task { await loadMore() } } }
                }
                if loadingMore { HStack { Spacer(); ProgressView(); Spacer() } }
                if let loadMoreError { Button("\(loadMoreError) · 重试") { Task { await loadMore() } }.font(.caption).foregroundStyle(.red) }
            }
        }
        .accessibilityIdentifier("players-list")
        .accessibilityValue("已加载 \(players.count)")
        .refreshable { await load(force: true) }.scrollContentBackground(.hidden).pageBackground()
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { state = .idle; players = []; return }
        state = .loading
        do {
            let query = scope.queryItems + [URLQueryItem(name: "limit", value: "30"), URLQueryItem(name: "offset", value: "0")]
            let result = try await app.api.get("/api/players", queryItems: query, as: PlayersResponse.self, forceRefresh: force)
            players = result.value.players; pagination = result.value.pagination
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError { return }
        catch { state = .failed(error.localizedDescription) }
    }

    private func loadMore() async {
        guard !loadingMore, pagination?.hasMore == true, let scope = app.selectedScope else { return }
        loadingMore = true; loadMoreError = nil
        defer { loadingMore = false }
        do {
            let query = scope.queryItems + [URLQueryItem(name: "limit", value: "30"), URLQueryItem(name: "offset", value: String(players.count))]
            let result = try await app.api.get("/api/players", queryItems: query, as: PlayersResponse.self, forceRefresh: true)
            let existing = Set(players.map(\.id)); players.append(contentsOf: result.value.players.filter { !existing.contains($0.id) }); pagination = result.value.pagination
        } catch is CancellationError { return }
        catch { loadMoreError = error.localizedDescription }
    }
}
