import SwiftUI

struct TeamDetailView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let teamID: String
    @State private var state: LoadState<TeamDetailResponse> = .idle

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else { switch state {
            case .idle, .loading: LoadingContent(label: "正在读取战队详情")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale): content(payload, stale: stale)
            } }
        }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("战队对比", systemImage: "arrow.left.arrow.right") { router.navigate(to: .compare(kind: .team, leftID: teamID)) } }
        .task(id: app.selectedScope) { await load() }
    }

    private var title: String { if case .loaded(let payload, _) = state { payload.team.shortName ?? payload.team.name } else { "战队详情" } }

    private func content(_ payload: TeamDetailResponse, stale: Bool) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                if stale { StaleBanner() }
                HStack(spacing: 18) {
                    RemoteImage(url: app.api.assetURL(payload.team.logo), size: 90, circular: false)
                    VStack(alignment: .leading, spacing: 6) { Text(payload.team.shortName ?? payload.team.name).font(.largeTitle.bold()); Text("\(payload.team.statusLabel ?? "") · \(payload.team.guild ?? "未加入门派")").font(.subheadline).foregroundStyle(.secondary); PowerBadge(rating: payload.team.powerRating) }
                    Spacer()
                }.padding(18).background(Brand.card, in: RoundedRectangle(cornerRadius: 20))
                if let notes = payload.team.notes, !notes.isEmpty { Text(notes).font(.subheadline).foregroundStyle(.secondary) }
                if let metrics = payload.metrics { MetricGrid(metrics: Array(metrics.prefix(6))) }
                if let achievements = payload.achievements, !achievements.isEmpty {
                    VStack(alignment: .leading, spacing: 10) { SectionHeading(title: "战队成就"); ForEach(achievements) { item in HStack { VStack(alignment: .leading) { Text(item.title).font(.headline); Text(item.meta ?? item.description ?? "").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(item.code).font(.caption.bold()).foregroundStyle(Brand.gold) }.padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) } }
                }
                if let roster = payload.roster, !roster.isEmpty {
                    VStack(alignment: .leading, spacing: 10) { SectionHeading(title: "出赛阵容", note: "\(roster.count) 人"); ForEach(roster) { player in Button { router.navigate(to: .player(player.playerID)) } label: { HStack { RemoteImage(url: app.api.assetURL(player.photo)); VStack(alignment: .leading) { Text(player.title).font(.headline); Text("\(player.topRole ?? "角色待录入") · \(player.matches ?? 0) 局 · 胜率 \(player.winRate ?? "--")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(player.points?.text ?? "--").bold(); Image(systemName: "chevron.right") } }.buttonStyle(.plain) } }
                }
                if let matches = payload.matches, !matches.isEmpty {
                    VStack(alignment: .leading, spacing: 10) { SectionHeading(title: "最近比赛"); ForEach(matches) { match in Button { router.navigate(to: .match(match.matchID)) } label: { HStack { VStack(alignment: .leading) { Text("\(match.playedOn ?? "") · 第\(match.round ?? 0)轮第\(match.gameNo ?? 0)局").font(.headline); Text("\(match.stageLabel ?? "") · \(match.result ?? "--")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(match.points?.text ?? "--").bold(); Image(systemName: "chevron.right") }.padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) }.buttonStyle(.plain) } }
                }
            }.padding()
        }.refreshable { await load(force: true) }.pageBackground()
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }; state = .loading
        do { let result = try await app.api.get("/api/teams/\(teamID)", queryItems: scope.queryItems, as: TeamDetailResponse.self, forceRefresh: force); state = .loaded(result.value, isStale: result.isStale) }
        catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }
}

