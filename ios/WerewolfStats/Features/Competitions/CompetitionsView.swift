import SwiftUI

struct CompetitionsView: View {
    @Environment(AppState.self) private var app
    @State private var state: LoadState<CompetitionResponse> = .idle
    @State private var expandedCity = ""

    var body: some View {
        Group {
            switch state {
            case .idle, .loading:
                LoadingContent(label: "正在读取赛事列表")
            case .failed(let message):
                ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale):
                content(payload, stale: stale)
            }
        }
        .navigationTitle("赛事")
        .task { await load() }
    }

    private func content(_ payload: CompetitionResponse, stale: Bool) -> some View {
        let groups = payload.resolvedCityGroups
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                if stale { StaleBanner() }
                BrandHero(
                    eyebrow: payload.generatedAt ?? "Competitions",
                    title: payload.hero?.title ?? "赛事入口",
                    copy: payload.hero?.copy ?? "按城市展开赛事，再选择要进入的赛季。"
                )
                if let metrics = payload.metrics, !metrics.isEmpty {
                    MetricGrid(metrics: Array(metrics.prefix(4)))
                }
                currentScope
                SectionHeading(
                    title: "城市赛事",
                    note: "\(groups.reduce(0) { $0 + $1.cards.count }) 个赛事"
                )
                ForEach(groups) { group in
                    CityCompetitionSection(
                        group: group,
                        expanded: expandedCity == group.regionName,
                        toggle: { toggle(group.regionName) }
                    )
                }
                if groups.isEmpty {
                    ContentUnavailableView(
                        "暂无城市赛事",
                        systemImage: "trophy",
                        description: Text("网站后台创建城市和赛事后会显示在这里。")
                    )
                }
            }
            .padding()
        }
        .refreshable { await load(force: true) }
        .pageBackground()
    }

    @ViewBuilder private var currentScope: some View {
        if let scope = app.selectedScope {
            VStack(alignment: .leading, spacing: 5) {
                Text("当前已进入").font(.caption.bold()).foregroundStyle(Brand.gold)
                Text(scope.competition).font(.headline)
                Text(scope.subtitle).font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(Brand.paleGold.opacity(0.35), in: RoundedRectangle(cornerRadius: 16))
            .accessibilityIdentifier("competition-current-scope")
        }
    }

    private func toggle(_ city: String) {
        withAnimation(.snappy) {
            expandedCity = expandedCity == city ? "" : city
        }
    }

    private func load(force: Bool = false) async {
        state = .loading
        do {
            let result = try await app.api.get(
                "/api/competitions",
                queryItems: [URLQueryItem(name: "grouped", value: "1")],
                as: CompetitionResponse.self,
                forceRefresh: force
            )
            let cities = result.value.resolvedCityGroups.map(\.regionName)
            if !cities.contains(expandedCity) {
                expandedCity = cities.contains(app.selectedScope?.region ?? "")
                    ? app.selectedScope?.region ?? ""
                    : cities.first ?? ""
            }
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError {
            return
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

private struct CityCompetitionSection: View {
    let group: CompetitionCityGroup
    let expanded: Bool
    let toggle: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            Button(action: toggle) {
                HStack(spacing: 12) {
                    Image(systemName: "building.2.fill")
                        .foregroundStyle(Brand.gold)
                        .frame(width: 34, height: 34)
                        .background(Brand.paleGold.opacity(0.45), in: Circle())
                    VStack(alignment: .leading, spacing: 4) {
                        Text(group.regionName).font(.headline)
                        Text("\(group.competitionCount ?? group.cards.count) 个赛事 · 最近 \(group.latestPlayedOn ?? "待更新")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(expanded ? "收起" : "展开").font(.caption.bold()).foregroundStyle(Brand.blue)
                    Image(systemName: "chevron.right")
                        .font(.caption.bold())
                        .rotationEffect(.degrees(expanded ? 90 : 0))
                }
                .contentShape(Rectangle())
                .padding(14)
                .background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("competition-city-\(group.regionName)")
            .accessibilityValue(expanded ? "已展开" : "已收起")

            if expanded {
                LazyVStack(spacing: 12) {
                    ForEach(group.cards) { card in
                        CompetitionCardView(card: card)
                    }
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
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

    private var stats: SeasonStats? { card.seasonStats?[season] }
    private var selected: Bool {
        app.selectedScope?.competition == card.competitionName && app.selectedScope?.season == season
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(card.seriesName).font(.caption.bold()).foregroundStyle(Brand.gold)
                    Text(card.competitionName).font(.title3.bold())
                    Text("最近 \(stats?.latestPlayedOn ?? card.latestPlayedOn ?? "待更新")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if selected {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                }
            }
            if !card.seasons.isEmpty {
                Picker("赛季", selection: $season) {
                    ForEach(card.seasons, id: \.self) { Text($0).tag($0) }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("competition-season-\(card.id)")
            }
            HStack {
                Label("\(stats?.teamCount ?? card.teamCount ?? 0) 队", systemImage: "shield")
                Label("\(stats?.playerCount ?? card.playerCount ?? 0) 人", systemImage: "person.2")
                Label("\(stats?.matchCount ?? card.matchCount ?? 0) 场", systemImage: "list.number")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            Button(selected ? "重新进入当前赛季" : "进入该赛季") {
                app.select(card.scope(for: season))
            }
            .buttonStyle(.borderedProminent)
            .frame(maxWidth: .infinity, alignment: .trailing)
            .accessibilityIdentifier("competition-enter-\(card.id)")
        }
        .padding(16)
        .background(selected ? Brand.paleGold.opacity(0.32) : Brand.card, in: RoundedRectangle(cornerRadius: 18))
        .accessibilityElement(children: .contain)
    }
}
