import SwiftUI

struct MatchDetailView: View {
    @Environment(AppState.self) private var app
    @Environment(RouterPath.self) private var router
    let matchID: String
    @State private var state: LoadState<MatchDetailResponse> = .idle

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else { switch state {
            case .idle, .loading: LoadingContent(label: "正在读取比赛详情")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, let stale): content(payload, stale: stale)
            } }
        }
        .navigationTitle("比赛详情").navigationBarTitleDisplayMode(.inline)
        .toolbar { if case .loaded(let payload, _) = state { Button("比赛日", systemImage: "calendar") { if let date = payload.match.playedOn { router.navigate(to: .day(date)) } } } }
        .task(id: app.selectedScope) { await load() }
    }

    private func content(_ payload: MatchDetailResponse, stale: Bool) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 20) {
                if stale { StaleBanner() }
                BrandHero(
                    eyebrow: payload.match.playedOn ?? "比赛",
                    title: "第\(payload.match.round ?? 0)轮第\(payload.match.gameNo ?? 0)局",
                    copy: "\(payload.match.stage ?? "") · \(payload.match.tableLabel ?? "") · \(payload.match.format ?? "")"
                )
                if let metrics = payload.metrics { MetricGrid(metrics: metrics) }
                VStack(alignment: .leading, spacing: 8) {
                    Label("胜利阵营：\(payload.match.winningCamp ?? "待录入")", systemImage: "flag.checkered")
                    if let duration = payload.match.durationMinutes { Label("\(duration) 分钟", systemImage: "clock") }
                    if let notes = payload.match.notes, !notes.isEmpty { Text(notes).font(.caption).foregroundStyle(.secondary) }
                }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Brand.card, in: RoundedRectangle(cornerRadius: 16))
                if let awards = payload.awards, !awards.isEmpty { awardsSection(awards) }
                if let scores = payload.teamScores, !scores.isEmpty { scoreSection(scores) }
                if let participants = payload.participants, !participants.isEmpty { participantSection(participants) }
                if let predictions = payload.scorePredictions, !predictions.isEmpty { predictionSection(predictions) }
            }.padding()
        }.refreshable { await load(force: true) }.pageBackground()
    }

    private func awardsSection(_ awards: [MatchAward]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "本局荣誉")
            ForEach(awards) { award in
                Button { if let id = award.playerID { router.navigate(to: .player(id)) } } label: {
                    HStack { Text(award.label).font(.caption.bold()).foregroundStyle(Brand.gold); VStack(alignment: .leading) { Text(award.playerName ?? "暂未设置").font(.headline); Text(award.meta ?? "").font(.caption).foregroundStyle(.secondary) }; Spacer() }
                        .padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                }.buttonStyle(.plain).disabled(award.playerID == nil)
            }
        }
    }

    private func scoreSection(_ scores: [MatchTeamScore]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "战队得分")
            ForEach(scores.sorted { ($0.points?.text ?? "") > ($1.points?.text ?? "") }) { score in
                Button { router.navigate(to: .team(score.teamID)) } label: {
                    HStack { VStack(alignment: .leading) { Text(score.teamName).font(.headline); Text(score.groupLabel ?? "").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(score.points?.text ?? "--").font(.title3.bold()); Image(systemName: "chevron.right") }
                        .padding(12).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                }.buttonStyle(.plain)
            }
        }
    }

    private func participantSection(_ players: [MatchParticipant]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "参赛选手", note: "\(players.count) 人")
            ForEach(players.sorted { $0.seat < $1.seat }) { player in
                Button { router.navigate(to: .player(player.playerID)) } label: {
                    HStack { Text("\(player.seat)").font(.caption.bold()).foregroundStyle(.white).frame(width: 30, height: 30).background(Brand.navy, in: Circle()); VStack(alignment: .leading) { Text(player.playerName).font(.headline); Text("\(player.teamName ?? "") · \(player.role ?? "") · \(player.result ?? "")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(player.points?.text ?? "--").bold(); Image(systemName: "chevron.right") }
                        .padding(10).background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
                }.buttonStyle(.plain)
            }
        }
    }

    private func predictionSection(_ predictions: [MatchPrediction]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { SectionHeading(title: "赛前预测"); Spacer(); Button("完整预测") { router.navigate(to: .predictions(playedOn: nil, matchID: matchID)) }.font(.caption) }
            ForEach(predictions) { item in HStack { VStack(alignment: .leading) { Text(item.playerName).font(.headline); Text("\(item.teamName ?? "") · \(item.confidence ?? "") · 预期胜率 \(item.expectedWinRate ?? "--")").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(item.expectedPoints?.text ?? "--").bold() }.padding(10).background(Brand.card, in: RoundedRectangle(cornerRadius: 14)) }
        }
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }; state = .loading
        do { let result = try await app.api.get("/api/matches/\(matchID)", queryItems: scope.queryItems, as: MatchDetailResponse.self, forceRefresh: force); state = .loaded(result.value, isStale: result.isStale) }
        catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }
}

