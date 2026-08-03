import SwiftUI

struct GuildDetailView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let guildID: String
    @State private var state: LoadState<GuildDetailResponse> = .idle

    var body: some View {
        Group { switch state {
        case .idle, .loading: LoadingContent(label: "正在读取门派详情")
        case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
        case .loaded(let payload, let stale): content(payload, stale: stale)
        } }
        .navigationTitle(title).navigationBarTitleDisplayMode(.inline).task { await load() }
    }

    private var title: String { if case .loaded(let payload, _) = state { payload.guild.name } else { "门派详情" } }

    private func content(_ payload: GuildDetailResponse, stale: Bool) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                if stale { StaleBanner() }
                BrandHero(eyebrow: "长期门派", title: payload.guild.name, copy: payload.guild.notes ?? "查看门派历届战队与荣誉。")
                if let metrics = payload.metrics { MetricGrid(metrics: Array(metrics.prefix(4))) }
                if let honors = payload.honors, !honors.isEmpty { VStack(alignment: .leading, spacing: 10) { SectionHeading(title: "历届荣誉"); ForEach(honors) { honor in HStack { Image(systemName: "medal.fill").foregroundStyle(Brand.gold); VStack(alignment: .leading) { Text(honor.title).font(.headline); Text("\(honor.teamName ?? "") · \(honor.scope ?? "")").font(.caption).foregroundStyle(.secondary) }; Spacer() }.padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) } } }
                teamSection("进行中的赛季战队", payload.ongoingTeams ?? [])
                ForEach(payload.historySections ?? []) { section in teamSection(section.competitionName, section.rows) }
            }.padding()
        }.refreshable { await load(force: true) }.pageBackground()
    }

    private func teamSection(_ title: String, _ teams: [GuildTeam]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if !teams.isEmpty { SectionHeading(title: title, note: "\(teams.count) 支") }
            ForEach(teams) { team in Button { router.navigate(to: .team(team.teamID)) } label: { HStack { VStack(alignment: .leading) { Text(team.teamName).font(.headline); Text("\(team.seasonName ?? "") · \(team.matches ?? 0) 场 · \(team.playerCount ?? 0) 人").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(team.pointsTotal?.text ?? "--").bold(); Image(systemName: "chevron.right") }.padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) }.buttonStyle(.plain) }
        }
    }

    private func load(force: Bool = false) async {
        state = .loading
        do { let result = try await app.api.get("/api/guilds/\(guildID)", as: GuildDetailResponse.self, forceRefresh: force); state = .loaded(result.value, isStale: result.isStale) }
        catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }
}
