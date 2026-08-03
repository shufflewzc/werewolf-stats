import SwiftUI

struct PredictionsView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let initialDay: String?
    let initialMatchID: String?
    @State private var state: LoadState<PredictionsResponse> = .idle
    @State private var selectedDay = ""
    @State private var predictions: [Prediction] = []
    @State private var pagination: Pagination?
    @State private var loadingMore = false
    @State private var loadMoreError: String?

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else { switch state {
            case .idle, .loading: LoadingContent(label: "正在计算胜率预测")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale): content(payload, stale: stale)
            } }
        }
        .navigationTitle("胜率预测").navigationBarTitleDisplayMode(.inline)
        .task(id: app.selectedScope) { selectedDay = initialDay ?? ""; await load() }
    }

    private func content(_ payload: PredictionsResponse, stale: Bool) -> some View {
        List {
            if stale { StaleBanner().listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            if let notice = payload.notice, !notice.isEmpty { Text(notice).font(.caption).foregroundStyle(.secondary) }
            if let days = payload.days, !days.isEmpty {
                Section("比赛日") {
                    ScrollView(.horizontal) { HStack { ForEach(days) { day in Button(day.playedOn) { selectedDay = day.playedOn; Task { await load(force: true) } }.buttonStyle(.borderedProminent).tint(selectedDay == day.playedOn ? Brand.gold : Brand.blue) } }.padding(.vertical, 4) }.scrollIndicators(.hidden)
                }
            }
            if let bands = payload.bandSummary, !bands.isEmpty { Section("预测分区") { MetricGrid(metrics: bands.map { Metric(label: $0.copy ?? $0.label, value: $0.value ?? .null, copy: $0.label) }).listRowInsets(EdgeInsets()).listRowBackground(Color.clear) } }
            Section("选手预测") {
                ForEach(predictions) { item in
                    Button { router.navigate(to: .player(item.playerID)) } label: {
                        HStack { RankBadge(rank: item.rank); VStack(alignment: .leading, spacing: 4) { Text(item.playerName).font(.headline); Text("\(item.teamName ?? "") · 胜率 \(item.winRate ?? "--") · \(item.confidence ?? "")").font(.caption).foregroundStyle(.secondary); if let labels = item.matchLabels, !labels.isEmpty { Text(labels.first ?? "").font(.caption2).foregroundStyle(.secondary).lineLimit(1) } }; Spacer(); VStack { Text(item.scoreText).font(.headline); Text("预期分").font(.caption2).foregroundStyle(.secondary) } }
                    }.buttonStyle(.plain).onAppear { if item.id == predictions.last?.id { Task { await loadMore() } } }
                }
                if loadingMore { HStack { Spacer(); ProgressView(); Spacer() } }
                if let loadMoreError { Button("\(loadMoreError) · 重试") { Task { await loadMore() } }.font(.caption).foregroundStyle(.red) }
            }
        }.refreshable { await load(force: true) }.scrollContentBackground(.hidden).pageBackground()
    }

    private func query(offset: Int) -> [URLQueryItem] {
        (app.selectedScope?.queryItems ?? []) + [
            URLQueryItem(name: "played_on", value: selectedDay),
            URLQueryItem(name: "match_id", value: initialMatchID ?? ""),
            URLQueryItem(name: "limit", value: "30"),
            URLQueryItem(name: "offset", value: String(offset))
        ]
    }

    private func load(force: Bool = false) async {
        guard app.selectedScope != nil else { return }; state = .loading
        do {
            let result = try await app.api.get("/api/predictions", queryItems: query(offset: 0), as: PredictionsResponse.self, forceRefresh: force)
            predictions = result.value.predictions; pagination = result.value.pagination
            if selectedDay.isEmpty { selectedDay = result.value.selectedDay?.playedOn ?? result.value.days?.first?.playedOn ?? "" }
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }

    private func loadMore() async {
        guard !loadingMore, pagination?.hasMore == true else { return }; loadingMore = true; loadMoreError = nil
        defer { loadingMore = false }
        do {
            let result = try await app.api.get("/api/predictions", queryItems: query(offset: predictions.count), as: PredictionsResponse.self, forceRefresh: true)
            let existing = Set(predictions.map(\.id)); predictions.append(contentsOf: result.value.predictions.filter { !existing.contains($0.id) }); pagination = result.value.pagination
        } catch is CancellationError { return } catch { loadMoreError = error.localizedDescription }
    }
}
