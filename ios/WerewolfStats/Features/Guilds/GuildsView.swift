import SwiftUI

struct GuildsView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    @State private var state: LoadState<GuildsResponse> = .idle

    var body: some View {
        Group {
            switch state {
            case .idle, .loading: LoadingContent(label: "正在读取门派")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale):
                ScrollView {
                    LazyVStack(spacing: 14) {
                        if stale { StaleBanner() }
                        if let metrics = payload.metrics { MetricGrid(metrics: Array(metrics.prefix(4))) }
                        ForEach(payload.cards) { guild in
                            Button { router.navigate(to: .guild(guild.guildID)) } label: {
                                HStack(spacing: 14) {
                                    Image(systemName: "shield.lefthalf.filled").font(.title).foregroundStyle(Brand.gold).frame(width: 48, height: 48).background(Brand.navy, in: RoundedRectangle(cornerRadius: 14))
                                    VStack(alignment: .leading, spacing: 4) { Text(guild.name).font(.headline); Text("\(guild.ongoingTeamCount ?? 0) 支进行中 · \(guild.matchCount ?? 0) 场 · \(guild.honorCount ?? 0) 项荣誉").font(.caption).foregroundStyle(.secondary) }
                                    Spacer(); Image(systemName: "chevron.right")
                                }.padding(14).background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
                            }.buttonStyle(.plain)
                        }
                    }.padding()
                }.refreshable { await load(force: true) }.pageBackground()
            }
        }.navigationTitle("门派").task { await load() }
    }

    private func load(force: Bool = false) async {
        state = .loading
        do {
            let result = try await app.api.get("/api/guilds", as: GuildsResponse.self, forceRefresh: force)
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError { return }
        catch { state = .failed(error.localizedDescription) }
    }
}
