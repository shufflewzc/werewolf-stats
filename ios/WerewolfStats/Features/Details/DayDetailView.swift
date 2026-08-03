import SwiftUI

struct DayDetailView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let playedOn: String
    @State private var state: LoadState<DayDetailResponse> = .idle
    @State private var board = "teams"

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else { switch state {
            case .idle, .loading: LoadingContent(label: "正在读取比赛日")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale): content(payload, stale: stale)
            } }
        }
        .navigationTitle(playedOn).navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("当日预测", systemImage: "chart.line.uptrend.xyaxis") { router.navigate(to: .predictions(playedOn: playedOn, matchID: nil)) } }
        .task(id: app.selectedScope) { await load() }
    }

    private func content(_ payload: DayDetailResponse, stale: Bool) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                if stale { StaleBanner() }
                BrandHero(eyebrow: "比赛日中心", title: playedOn, copy: payload.hero?.copy ?? "查看当天赛程、榜单和赛事日报。")
                if let metrics = payload.metrics { MetricGrid(metrics: metrics) }
                aiReport(payload.aiReport)
                dayBoards(payload)
                if let competitions = payload.competitions {
                    ForEach(competitions) { competition in
                        VStack(alignment: .leading, spacing: 10) {
                            SectionHeading(title: competition.competitionName, note: "\(competition.matches?.count ?? 0) 场")
                            ForEach(competition.matches ?? []) { match in
                                Button { router.navigate(to: .match(match.matchID)) } label: { HStack { VStack(alignment: .leading) { Text("第\(match.round ?? 0)轮第\(match.gameNo ?? 0)局").font(.headline); Text(match.tableLabel ?? match.stage ?? "").font(.caption).foregroundStyle(.secondary) }; Spacer(); Image(systemName: "chevron.right") }.padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) }.buttonStyle(.plain)
                            }
                        }
                    }
                }
            }.padding()
        }.refreshable { await load(force: true) }.pageBackground()
    }

    @ViewBuilder private func aiReport(_ report: AIReport?) -> some View {
        if let report {
            VStack(alignment: .leading, spacing: 8) {
                SectionHeading(title: "AI 比赛日报", note: report.generatedAt)
                Text((report.content?.isEmpty == false ? report.content : report.emptyCopy) ?? "暂无日报")
                    .font(.subheadline).foregroundStyle(report.exists == true ? .primary : .secondary)
            }.padding(16).background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
        }
    }

    private func dayBoards(_ payload: DayDetailResponse) -> some View {
        let rows = board == "teams" ? (payload.teamLeaderboard ?? []) : (payload.playerLeaderboard ?? [])
        return VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "当日榜单", note: "\(rows.count) 名")
            Picker("榜单", selection: $board) { Text("战队").tag("teams"); Text("选手").tag("players") }.pickerStyle(.segmented)
            ForEach(rows.prefix(20)) { row in
                Button {
                    if let id = row.teamID { router.navigate(to: .team(id)) }
                    else if let id = row.playerID { router.navigate(to: .player(id)) }
                } label: { HStack { RankBadge(rank: row.rank); VStack(alignment: .leading) { Text(row.title).font(.headline); Text(row.winRate ?? row.teamName ?? "").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(row.valueText).bold(); Image(systemName: "chevron.right") }.padding(10).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) }.buttonStyle(.plain)
            }
        }
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }; state = .loading
        do { let result = try await app.api.get("/api/days/\(playedOn)", queryItems: scope.queryItems, as: DayDetailResponse.self, forceRefresh: force); state = .loaded(result.value, isStale: result.isStale) }
        catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }
}
