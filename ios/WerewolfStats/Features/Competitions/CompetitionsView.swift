import SwiftUI

struct CompetitionsView: View {
    @Environment(AppState.self) private var app
    @State private var state: LoadState<CompetitionResponse> = .idle

    var body: some View {
        Group {
            switch state {
            case .idle, .loading: LoadingContent(label: "正在读取赛事列表")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale):
                ScrollView {
                    LazyVStack(spacing: 16) {
                        if stale { StaleBanner() }
                        BrandHero(eyebrow: payload.generatedAt ?? "选择赛事", title: "赛事与赛季", copy: "选择后，首页、门派、选手和预测都会跟随当前范围。")
                        if let metrics = payload.metrics { MetricGrid(metrics: Array(metrics.prefix(4))) }
                        ForEach(payload.cards) { CompetitionCardView(card: $0) }
                        if payload.cards.isEmpty { ContentUnavailableView("暂无赛事", systemImage: "trophy", description: Text("网站后台录入赛事后会显示在这里。")) }
                    }.padding()
                }.refreshable { await load(force: true) }.pageBackground()
            }
        }
        .navigationTitle("赛事")
        .task { await load() }
    }

    private func load(force: Bool = false) async {
        state = .loading
        do {
            let result = try await app.api.get("/api/competitions", as: CompetitionResponse.self, forceRefresh: force)
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError { return }
        catch { state = .failed(error.localizedDescription) }
    }
}

private struct CompetitionCardView: View {
    @Environment(AppState.self) private var app
    let card: CompetitionCard
    @State private var season: String

    init(card: CompetitionCard) {
        self.card = card
        _season = State(initialValue: card.seasons.first ?? "")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(card.competitionName).font(.title3.bold())
                    Text("\(card.regionName) · \(card.seriesName)").font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                if app.selectedScope?.competition == card.competitionName, app.selectedScope?.season == season { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green) }
            }
            if !card.seasons.isEmpty {
                Picker("赛季", selection: $season) { ForEach(card.seasons, id: \.self) { Text($0).tag($0) } }.pickerStyle(.menu)
            }
            let stats = card.seasonStats?[season]
            HStack {
                Label("\(stats?.teamCount ?? card.teamCount ?? 0) 队", systemImage: "shield")
                Label("\(stats?.playerCount ?? card.playerCount ?? 0) 人", systemImage: "person.2")
                Label("\(stats?.matchCount ?? card.matchCount ?? 0) 场", systemImage: "list.number")
            }.font(.caption).foregroundStyle(.secondary)
            Button(app.selectedScope?.competition == card.competitionName && app.selectedScope?.season == season ? "重新进入当前赛季" : "进入该赛季") {
                app.select(card.scope(for: season))
            }.buttonStyle(.borderedProminent).frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(16).background(Brand.card, in: RoundedRectangle(cornerRadius: 18))
        .accessibilityElement(children: .contain)
    }
}

