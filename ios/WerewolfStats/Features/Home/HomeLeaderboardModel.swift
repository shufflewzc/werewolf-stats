import Foundation

enum LeaderboardBoard: String, CaseIterable, Identifiable, Sendable {
    case teams
    case players
    case mvp
    case svp

    var id: String { rawValue }

    var title: String {
        switch self {
        case .teams: "战队积分"
        case .players: "个人积分"
        case .mvp: "个人MVP"
        case .svp: "个人SVP"
        }
    }
}

struct LeaderboardSelection: Equatable, Sendable {
    var board: LeaderboardBoard = .teams
    var stageKey = "all"
    var teamSectionKey = ""

    mutating func normalize(for payload: DashboardResponse) {
        let stageKeys = Set(payload.resolvedLeaderboardStages.map(\.key))
        if !stageKeys.contains(stageKey) {
            stageKey = "all"
        }
        normalizeTeamSection(for: payload)
    }

    mutating func selectStage(_ key: String, in payload: DashboardResponse) {
        stageKey = key
        normalize(for: payload)
    }

    mutating func selectBoard(_ board: LeaderboardBoard) {
        self.board = board
    }

    mutating func selectTeamSection(_ key: String, in payload: DashboardResponse) {
        guard payload.teamSections(for: stageKey).contains(where: { $0.key == key }) else { return }
        teamSectionKey = key
    }

    private mutating func normalizeTeamSection(for payload: DashboardResponse) {
        let sections = payload.teamSections(for: stageKey)
        if !sections.contains(where: { $0.key == teamSectionKey }) {
            teamSectionKey = sections.first?.key ?? ""
        }
    }
}

extension DashboardResponse {
    var resolvedLeaderboardStages: [LeaderboardStage] {
        let stages = leaderboardStages ?? []
        guard !stages.isEmpty else { return [LeaderboardStage(key: "all", label: "全部")] }
        guard !stages.contains(where: { $0.key == "all" }) else { return stages }
        return [LeaderboardStage(key: "all", label: "全部")] + stages
    }

    var resolvedTeamLeaderboardSections: [String: [TeamLeaderboardSection]] {
        var resolved = teamLeaderboardSections ?? [:]
        guard resolved["regular_season"] == nil,
              let legacy = regularSeasonTeamLeaderboards,
              !legacy.isEmpty
        else { return resolved }

        let priority = ["S": 0, "F": 1]
        let keys = legacy.keys.sorted { left, right in
            switch (priority[left], priority[right]) {
            case let (.some(leftIndex), .some(rightIndex)):
                return leftIndex < rightIndex
            case (.some, .none):
                return true
            case (.none, .some):
                return false
            case (.none, .none):
                return left.localizedStandardCompare(right) == .orderedAscending
            }
        }
        resolved["regular_season"] = keys.map { key in
            TeamLeaderboardSection(
                key: key,
                label: "\(key)组",
                title: "\(key)组常规赛榜",
                rows: legacy[key] ?? []
            )
        }
        return resolved
    }

    func teamSections(for stageKey: String) -> [TeamLeaderboardSection] {
        resolvedTeamLeaderboardSections[stageKey] ?? []
    }

    func leaderboardRows(for selection: LeaderboardSelection) -> [LeaderboardRow] {
        let sections = teamSections(for: selection.stageKey)
        if selection.board == .teams, !sections.isEmpty {
            return sections.first(where: { $0.key == selection.teamSectionKey })?.rows
                ?? sections.first?.rows
                ?? []
        }

        let boards = selection.stageKey == "all"
            ? leaderboards
            : leaderboardsByStage?[selection.stageKey]
        return boards?[selection.board.rawValue] ?? []
    }
}

struct LeaderboardDisplayRow: Identifiable, Hashable, Sendable {
    let row: LeaderboardRow
    let board: LeaderboardBoard

    var entityID: String { row.teamID ?? row.playerID ?? "\(row.rank ?? 0)-\(row.title)" }
    var id: String { "\(board.rawValue):\(entityID)" }

    var title: String { row.title }
    var isStarPlayer: Bool { row.isStarPlayer == true }
    var valueText: String { row.valueText }

    var valueLabel: String {
        switch board {
        case .teams, .players: "积分"
        case .mvp: row.awardLabel ?? "MVP"
        case .svp: row.awardLabel ?? "SVP"
        }
    }

    var metadata: String {
        switch board {
        case .teams:
            "胜率 \(row.winRate ?? "--") · 出赛 \(row.matchesRepresented ?? 0) 场"
        case .players:
            "\(row.teamName ?? "未绑定战队") · 出场 \(row.gamesPlayed ?? 0) 局"
        case .mvp, .svp:
            "\(row.teamName ?? "未绑定战队") · 最近 \(row.latestAwardedOn ?? "待更新")"
        }
    }

    var badges: [LeaderboardBadge] {
        if let badges = row.badges {
            return badges
        }

        var fallback: [LeaderboardBadge] = []
        if let group = nonempty(row.regularSeasonGroup ?? row.groupLabel) {
            fallback.append(
                LeaderboardBadge(
                    text: group,
                    style: group.hasPrefix("S") ? "gold" : "blue",
                    kind: "group"
                )
            )
        }
        if let progress = nonempty(row.progressStatus) {
            fallback.append(
                LeaderboardBadge(
                    text: progress,
                    style: Self.progressStyle(for: progress),
                    kind: "progress"
                )
            )
        }
        return fallback
    }

    private func nonempty(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return value
    }

    private static func progressStyle(for status: String) -> String {
        switch status {
        case "直通": "orange"
        case "晋级": "green"
        case "淘汰": "red"
        default: "gray"
        }
    }
}
