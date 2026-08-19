import SwiftUI

struct PredictionsView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let initialDay: String?
    let initialMatchID: String?

    @State private var state: LoadState<PredictionsResponse> = .idle
    @State private var selectedDay = ""
    @State private var selectedMatchID: String?
    @State private var predictions: [Prediction] = []
    @State private var pagination: Pagination?
    @State private var loadingMore = false
    @State private var loadMoreError: String?
    @State private var switchingDay = false
    @State private var switchingDayValue = ""
    @State private var switchDayError: String?

    var body: some View {
        Group {
            if app.selectedScope == nil {
                ScopeRequiredView()
            } else {
                switch state {
                case .idle, .loading:
                    LoadingContent(label: "正在计算胜率预测")
                case .failed(let message):
                    ErrorContent(message: message) { Task { await load(force: true) } }
                case .loaded(let payload, let stale):
                    content(payload, stale: stale)
                }
            }
        }
        .navigationTitle("当天三局胜率预测")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: app.selectedScope) {
            selectedDay = initialDay ?? ""
            selectedMatchID = initialMatchID
            await load()
        }
    }

    private func content(_ payload: PredictionsResponse, stale: Bool) -> some View {
        List {
            if stale {
                StaleBanner().listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            daySelector(payload.days ?? [])
            selectedDayCard(payload)
            if let bands = payload.bandSummary, !bands.isEmpty {
                Section("预测分区") {
                    MetricGrid(metrics: bands.map {
                        Metric(label: $0.copy ?? $0.label, value: $0.value ?? .null, copy: $0.label)
                    })
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                }
            }
            if let notice = payload.notice, !notice.isEmpty {
                Section {
                    Text(notice).font(.caption).foregroundStyle(.secondary)
                }
            }
            Section {
                ForEach(predictions) { item in
                    PredictionForecastRow(item: item) {
                        if item.canOpenProfile { router.navigate(to: .player(item.playerID)) }
                    }
                    .onAppear {
                        if item.id == predictions.last?.id { Task { await loadMore() } }
                    }
                }
                if predictions.isEmpty {
                    ContentUnavailableView(
                        "暂无预测数据",
                        systemImage: "chart.line.downtrend.xyaxis",
                        description: Text("这个比赛日还没有可计算的完整选手名单。")
                    )
                }
                if loadingMore {
                    HStack { Spacer(); ProgressView(); Spacer() }
                }
                if let loadMoreError {
                    Button("\(loadMoreError) · 重试") { Task { await loadMore() } }
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            } header: {
                HStack {
                    Text("当日预计总分")
                    Spacer()
                    Text("\(predictions.count) / \(pagination?.total ?? predictions.count) 人")
                }
            }
        }
        .refreshable { await load(force: true) }
        .scrollContentBackground(.hidden)
        .pageBackground()
    }

    @ViewBuilder private func daySelector(_ days: [PredictionDay]) -> some View {
        Section {
            if days.isEmpty {
                Text("录入当天赛程和名单后，这里会显示比赛日预测入口。")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 9) {
                        ForEach(days) { day in
                            let isSelected = selectedDay == day.playedOn
                            let isPending = switchingDayValue == day.playedOn
                            Button {
                                Task { await switchTo(day.playedOn) }
                            } label: {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 5) {
                                        Text(day.label ?? day.playedOn).font(.caption.bold()).lineLimit(1)
                                        if day.scenarioPublished == true {
                                            Image(systemName: "checkmark.seal.fill").font(.caption2)
                                        }
                                    }
                                    Text(isPending ? "切换中…" : "\(day.matchCount ?? 0) 场 · \(day.playerEntryCount ?? 0) 人次")
                                        .font(.caption2)
                                        .foregroundStyle(isSelected ? Color.white.opacity(0.8) : Color.secondary)
                                }
                                .foregroundStyle(isSelected ? Color.white : Color.primary)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 9)
                                .background(isSelected ? Brand.blue : Brand.card, in: RoundedRectangle(cornerRadius: 11))
                                .overlay {
                                    if isPending {
                                        RoundedRectangle(cornerRadius: 11).stroke(Brand.gold, lineWidth: 2)
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                            .disabled(switchingDay || isSelected)
                            .accessibilityIdentifier("prediction-day-\(day.playedOn)")
                            .accessibilityAddTraits(isSelected ? .isSelected : [])
                        }
                    }
                    .padding(.vertical, 2)
                }
                if let switchDayError {
                    Text(switchDayError).font(.caption).foregroundStyle(.red)
                }
            }
        } header: {
            HStack {
                Text("选择比赛日")
                Spacer()
                Text(switchingDay ? "正在切换" : "\(days.count) 天")
            }
        }
    }

    private func selectedDayCard(_ payload: PredictionsResponse) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                Text("当前比赛日").font(.caption.bold()).foregroundStyle(Brand.gold)
                Text(payload.selectedDay?.label ?? selectedDay.ifEmpty("尚未选择"))
                    .font(.title3.bold())
                Text("12 人随机模拟三局 · \(sourceDescription(payload))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if payload.isPredictionShareReady, let playedOn = payload.selectedDay?.playedOn {
                    Button("生成当天预测图", systemImage: "photo.on.rectangle.angled") {
                        router.navigate(to: .predictionShare(playedOn: playedOn))
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("prediction-share-card")
                    Text("生成后可系统分享或保存相册，图片内含直达当天预测的小程序码。")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func sourceDescription(_ payload: PredictionsResponse) -> String {
        if payload.scenario != nil { return "已发布场景" }
        if payload.rosterSource == "official_schedule" { return "正式赛程名单" }
        return "暂无完整名单"
    }

    private func query(offset: Int, day: String, matchID: String?) -> [URLQueryItem] {
        (app.selectedScope?.queryItems ?? []) + [
            URLQueryItem(name: "played_on", value: day),
            URLQueryItem(name: "match_id", value: matchID ?? ""),
            URLQueryItem(name: "limit", value: "30"),
            URLQueryItem(name: "offset", value: String(offset))
        ]
    }

    private func load(
        force: Bool = false,
        requestedDay: String? = nil,
        matchID: String? = nil,
        keepContent: Bool = false
    ) async {
        guard app.selectedScope != nil else { return }
        let day = requestedDay ?? selectedDay
        let requestedMatchID = matchID ?? selectedMatchID
        if !keepContent { state = .loading }
        do {
            let result = try await app.api.get(
                "/api/predictions",
                queryItems: query(offset: 0, day: day, matchID: requestedMatchID),
                as: PredictionsResponse.self,
                forceRefresh: force
            )
            predictions = result.value.predictions
            pagination = result.value.pagination
            selectedDay = result.value.selectedDay?.playedOn
                ?? result.value.days?.first?.playedOn
                ?? day
            selectedMatchID = nil
            loadMoreError = nil
            state = .loaded(result.value, isStale: result.isStale)
        } catch is CancellationError {
            return
        } catch {
            if keepContent {
                switchDayError = error.localizedDescription
            } else {
                state = .failed(error.localizedDescription)
            }
        }
    }

    private func switchTo(_ day: String) async {
        guard !switchingDay, day != selectedDay else { return }
        switchingDay = true
        switchingDayValue = day
        switchDayError = nil
        defer {
            switchingDay = false
            switchingDayValue = ""
        }
        await load(force: true, requestedDay: day, matchID: nil, keepContent: true)
    }

    private func loadMore() async {
        guard !switchingDay, !loadingMore, pagination?.hasMore == true else { return }
        loadingMore = true
        loadMoreError = nil
        defer { loadingMore = false }
        do {
            let result = try await app.api.get(
                "/api/predictions",
                queryItems: query(offset: predictions.count, day: selectedDay, matchID: nil),
                as: PredictionsResponse.self,
                forceRefresh: true
            )
            let existing = Set(predictions.map(\.id))
            predictions.append(contentsOf: result.value.predictions.filter { !existing.contains($0.id) })
            pagination = result.value.pagination
        } catch is CancellationError {
            return
        } catch {
            loadMoreError = error.localizedDescription
        }
    }
}

private struct PredictionForecastRow: View {
    let item: Prediction
    let openProfile: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(action: openProfile) {
                HStack {
                    RankBadge(rank: item.rank)
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 5) {
                            Text(item.playerName).font(.headline)
                            if item.isStarPlayer == true {
                                Image(systemName: "star.fill").font(.caption).foregroundStyle(Brand.gold)
                            }
                        }
                        Text(metadata).font(.caption).foregroundStyle(.secondary)
                        if !item.canOpenProfile {
                            Text("使用总体先验").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(item.scoreText).font(.headline)
                        Text(item.manualOverrideApplied == true ? "\(scoreBand) · 已修正" : scoreBand)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(!item.canOpenProfile)

            if let gameRates = item.gameWinDisplays, gameRates.count == 3 {
                HStack(spacing: 8) {
                    ForEach(Array(gameRates.enumerated()), id: \.offset) { index, value in
                        VStack(spacing: 3) {
                            Text("第\(index + 1)局胜率").font(.caption2).foregroundStyle(.secondary)
                            Text(value).font(.subheadline.bold())
                        }
                        .frame(maxWidth: .infinity)
                        .padding(8)
                        .background(Brand.card, in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
            if let distribution = item.winCountProbabilities, !distribution.isEmpty {
                Text(distribution.map { "\($0.wins)胜 \($0.display ?? String(format: "%.1f%%", $0.probability * 100))" }.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let markets = item.marketProbabilities, !markets.isEmpty {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    ForEach(markets) { market in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(market.label).font(.caption).foregroundStyle(.secondary)
                            Text(market.display ?? "--").font(.subheadline.bold())
                            Text("等于 \(market.equalityDisplay ?? "0.0%")")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .background(Brand.card, in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
            if let labels = item.matchLabels, !labels.isEmpty {
                Text(labels.joined(separator: " · "))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .accessibilityElement(children: .contain)
    }

    private var metadata: String {
        let team = item.teamName?.ifEmpty("未绑定战队") ?? "未绑定战队"
        if let expectedWins = item.expectedWins {
            return "\(team) · 预计 \(String(format: "%.2f", expectedWins)) 胜 · 置信度 \(item.confidence ?? "--")"
        }
        return "\(team) · 胜率 \(item.winRate ?? "--") · 置信度 \(item.confidence ?? "--")"
    }

    private var scoreBand: String {
        let value: Double
        switch item.expectedTotal ?? item.expectedPoints {
        case .number(let number): value = number
        case .string(let string): value = Double(string) ?? 0
        default: value = 0
        }
        if value >= 12 { return "高分区" }
        if value >= 7 { return "竞争区" }
        if value >= 5 { return "主体区" }
        return "观察区"
    }
}

private extension String {
    func ifEmpty(_ fallback: String) -> String { isEmpty ? fallback : self }
}
