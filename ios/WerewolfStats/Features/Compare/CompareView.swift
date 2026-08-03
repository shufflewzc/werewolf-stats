import SwiftUI

private struct CompareCandidate: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let image: String?
}

private struct ComparePayload {
    let left: CompareCandidate
    let right: CompareCandidate
    let rows: [CompareMetric]
    let isStale: Bool
}

private struct CompareMetric: Identifiable {
    let label: String
    let leftValue: String
    let rightValue: String
    var id: String { label }
}

struct CompareView: View {
    @Environment(AppState.self) private var app
    let kind: EntityKind
    let initialLeftID: String?
    @State private var candidates: [CompareCandidate] = []
    @State private var leftID = ""
    @State private var rightID = ""
    @State private var state: LoadState<ComparePayload> = .idle

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else { switch state {
            case .idle, .loading: LoadingContent(label: "正在准备对比")
            case .failed(let message): ErrorContent(message: message) { Task { await loadCandidates(force: true) } }
            case .loaded(let payload, _): content(payload)
            } }
        }
        .navigationTitle(kind == .team ? "战队对比" : "选手对比")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: app.selectedScope) { await loadCandidates() }
        .task(id: "\(leftID)|\(rightID)") { await loadComparison() }
    }

    private func content(_ payload: ComparePayload) -> some View {
        ScrollView {
            VStack(spacing: 18) {
                if payload.isStale { StaleBanner() }
                HStack(spacing: 12) {
                    candidatePicker(title: "左侧", selection: $leftID)
                    Button { swap(&leftID, &rightID) } label: { Image(systemName: "arrow.left.arrow.right").padding(10).background(Brand.paleGold, in: Circle()) }.buttonStyle(.plain).accessibilityLabel("交换对比对象")
                    candidatePicker(title: "右侧", selection: $rightID)
                }
                HStack(alignment: .top, spacing: 12) {
                    entityHeader(payload.left)
                    Text("VS").font(.caption.bold()).foregroundStyle(Brand.gold).padding(.top, 28)
                    entityHeader(payload.right)
                }
                VStack(spacing: 0) {
                    ForEach(payload.rows) { row in
                        HStack { Text(row.leftValue).font(.headline).frame(maxWidth: .infinity); Text(row.label).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity); Text(row.rightValue).font(.headline).frame(maxWidth: .infinity) }
                            .padding(.vertical, 13)
                        Divider()
                    }
                }.padding(.horizontal).background(Brand.card, in: RoundedRectangle(cornerRadius: 18))
            }.padding()
        }.pageBackground()
    }

    private func candidatePicker(title: String, selection: Binding<String>) -> some View {
        Picker(title, selection: selection) {
            ForEach(candidates) { Text($0.title).tag($0.id) }
        }.pickerStyle(.menu).frame(maxWidth: .infinity).padding(8).background(Brand.card, in: RoundedRectangle(cornerRadius: 12))
    }

    private func entityHeader(_ item: CompareCandidate) -> some View {
        VStack(spacing: 8) { RemoteImage(url: app.api.assetURL(item.image), size: 72, circular: kind == .player); Text(item.title).font(.headline).multilineTextAlignment(.center); Text(item.subtitle).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center) }
            .frame(maxWidth: .infinity)
    }

    private func loadCandidates(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }; state = .loading
        do {
            if kind == .team {
                let result = try await app.api.get("/api/teams", queryItems: scope.queryItems, as: TeamsResponse.self, forceRefresh: force)
                candidates = result.value.teams.map { CompareCandidate(id: $0.teamID, title: $0.shortName ?? $0.name, subtitle: "\($0.matchesRepresented ?? 0) 场 · \($0.winRate ?? "--")", image: $0.logo) }
            } else {
                let result = try await app.api.get("/api/players", queryItems: scope.queryItems + [URLQueryItem(name: "limit", value: "100"), URLQueryItem(name: "offset", value: "0")], as: PlayersResponse.self, forceRefresh: force)
                candidates = result.value.players.map { CompareCandidate(id: $0.playerID, title: $0.displayName, subtitle: "\($0.teamName ?? "未绑定战队") · \($0.gamesPlayed ?? 0) 局", image: $0.photo) }
            }
            guard candidates.count >= 2 else { state = .failed("当前赛事至少需要两个对象才能对比。"); return }
            leftID = candidates.contains(where: { $0.id == initialLeftID }) ? (initialLeftID ?? candidates[0].id) : candidates[0].id
            rightID = candidates.first(where: { $0.id != leftID })!.id
        } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }

    private func loadComparison() async {
        guard !leftID.isEmpty, !rightID.isEmpty, leftID != rightID, let scope = app.selectedScope,
              let left = candidates.first(where: { $0.id == leftID }), let right = candidates.first(where: { $0.id == rightID }) else { return }
        state = .loading
        do {
            let leftMetrics: APIResult<[Metric]>
            let rightMetrics: APIResult<[Metric]>
            if kind == .team {
                async let leftResult = app.api.get("/api/teams/\(leftID)", queryItems: scope.queryItems, as: TeamDetailResponse.self)
                async let rightResult = app.api.get("/api/teams/\(rightID)", queryItems: scope.queryItems, as: TeamDetailResponse.self)
                let (l, r) = try await (leftResult, rightResult)
                leftMetrics = APIResult(value: l.value.metrics ?? [], isStale: l.isStale)
                rightMetrics = APIResult(value: r.value.metrics ?? [], isStale: r.isStale)
            } else {
                async let leftResult = app.api.get("/api/players/\(leftID)", queryItems: scope.queryItems, as: PlayerDetailResponse.self)
                async let rightResult = app.api.get("/api/players/\(rightID)", queryItems: scope.queryItems, as: PlayerDetailResponse.self)
                let (l, r) = try await (leftResult, rightResult)
                leftMetrics = APIResult(value: l.value.metrics ?? [], isStale: l.isStale)
                rightMetrics = APIResult(value: r.value.metrics ?? [], isStale: r.isStale)
            }
            var labels: [String] = []
            for metric in leftMetrics.value + rightMetrics.value where !labels.contains(metric.label) { labels.append(metric.label) }
            let rows = labels.prefix(8).map { label in
                CompareMetric(label: label, leftValue: leftMetrics.value.first(where: { $0.label == label })?.value.text ?? "--", rightValue: rightMetrics.value.first(where: { $0.label == label })?.value.text ?? "--")
            }
            state = .loaded(ComparePayload(left: left, right: right, rows: rows, isStale: leftMetrics.isStale || rightMetrics.isStale), isStale: leftMetrics.isStale || rightMetrics.isStale)
        } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }
}

