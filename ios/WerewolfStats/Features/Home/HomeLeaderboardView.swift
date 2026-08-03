import SwiftUI

struct HomeLeaderboardView: View {
    let payload: DashboardResponse
    @Binding var selection: LeaderboardSelection
    let openRow: (LeaderboardRow) -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var sections: [TeamLeaderboardSection] {
        payload.teamSections(for: selection.stageKey)
    }

    private var rows: [LeaderboardDisplayRow] {
        payload.leaderboardRows(for: selection).map {
            LeaderboardDisplayRow(row: $0, board: selection.board)
        }
    }

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 12) {
            SectionHeading(title: "排行榜", note: "\(rows.count) 名")
            if payload.resolvedLeaderboardStages.count > 1 {
                stageSelector
            }
            boardSelector
            if selection.board == .teams, !sections.isEmpty {
                teamSectionSelector
            }
            if rows.isEmpty {
                Text("暂无榜单数据")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(rows) { row in
                        LeaderboardRowCard(row: row) {
                            openRow(row.row)
                        }
                    }
                }
                .accessibilityIdentifier("leaderboard-list")
                .accessibilityValue("已显示 \(rows.count) 名")
            }
        }
    }

    private var stageSelector: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            LazyHStack(spacing: 8) {
                ForEach(payload.resolvedLeaderboardStages) { stage in
                    selectionButton(
                        title: stage.label,
                        isSelected: selection.stageKey == stage.key,
                        identifier: "leaderboard-stage-\(stage.key)"
                    ) {
                        var updated = selection
                        updated.selectStage(stage.key, in: payload)
                        selection = updated
                    }
                }
            }
            .padding(.vertical, 2)
        }
    }

    @ViewBuilder private var boardSelector: some View {
        if dynamicTypeSize.isAccessibilitySize {
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 8) {
                    ForEach(LeaderboardBoard.allCases) { board in
                        boardButton(board, fillsWidth: false)
                    }
                }
                .padding(.vertical, 2)
            }
        } else {
            HStack(spacing: 6) {
                ForEach(LeaderboardBoard.allCases) { board in
                    boardButton(board, fillsWidth: true)
                }
            }
        }
    }

    private var teamSectionSelector: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            LazyHStack(spacing: 8) {
                ForEach(sections) { section in
                    selectionButton(
                        title: section.title,
                        isSelected: selection.teamSectionKey == section.key,
                        identifier: "leaderboard-section-\(section.key)"
                    ) {
                        var updated = selection
                        updated.selectTeamSection(section.key, in: payload)
                        selection = updated
                    }
                }
            }
            .padding(.vertical, 2)
        }
    }

    private func boardButton(_ board: LeaderboardBoard, fillsWidth: Bool) -> some View {
        let isSelected = selection.board == board
        return Button {
            var updated = selection
            updated.selectBoard(board)
            selection = updated
        } label: {
            Text(board.title)
                .font(.caption.bold())
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(isSelected ? Color.white : Color.primary)
                .frame(maxWidth: fillsWidth ? .infinity : nil)
                .padding(.horizontal, fillsWidth ? 8 : 14)
                .padding(.vertical, 10)
                .background(isSelected ? Brand.navy : Brand.card, in: RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("leaderboard-board-\(board.rawValue)")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    private func selectionButton(
        title: String,
        isSelected: Bool,
        identifier: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.bold())
                .foregroundStyle(isSelected ? Color.white : Color.primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(isSelected ? Brand.blue : Brand.card, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

private struct LeaderboardRowCard: View {
    let row: LeaderboardDisplayRow
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                RankBadge(rank: row.row.rank)
                VStack(alignment: .leading, spacing: 4) {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 6) {
                            title
                            badges
                        }
                        VStack(alignment: .leading, spacing: 5) {
                            title
                            badges
                        }
                    }
                    Text(row.metadata)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 2) {
                    Text(row.valueText).font(.headline)
                    Text(row.valueLabel).font(.caption2).foregroundStyle(.secondary)
                }
                Image(systemName: "chevron.right")
                    .font(.caption.bold())
                    .foregroundStyle(.tertiary)
            }
            .padding(12)
            .background(Brand.card, in: RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("leaderboard-row-\(row.board.rawValue)-\(row.entityID)")
    }

    private var title: some View {
        HStack(spacing: 5) {
            Text(row.title).font(.headline)
            if row.isStarPlayer {
                Image(systemName: "star.fill")
                    .font(.caption)
                    .foregroundStyle(Brand.gold)
                    .accessibilityLabel("明星选手")
            }
        }
    }

    @ViewBuilder private var badges: some View {
        if !row.badges.isEmpty {
            HStack(spacing: 4) {
                ForEach(Array(row.badges.enumerated()), id: \.offset) { _, badge in
                    LeaderboardBadgeView(badge: badge)
                }
            }
        }
    }
}

private struct LeaderboardBadgeView: View {
    let badge: LeaderboardBadge

    var body: some View {
        Text(badge.text)
            .font(.caption2.bold())
            .foregroundStyle(foreground)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(background, in: Capsule())
            .accessibilityLabel("\(badge.kind ?? "标签")：\(badge.text)")
    }

    private var foreground: Color {
        switch badge.style {
        case "gold": Brand.navy
        case "blue": Brand.blue
        case "orange": .orange
        case "green": .green
        case "red": .red
        default: .secondary
        }
    }

    private var background: Color {
        switch badge.style {
        case "gold": Brand.paleGold
        case "blue": Brand.blue.opacity(0.14)
        case "orange": Color.orange.opacity(0.15)
        case "green": Color.green.opacity(0.15)
        case "red": Color.red.opacity(0.15)
        default: Color.secondary.opacity(0.12)
        }
    }
}

#if DEBUG
private struct HomeLeaderboardPreview: View {
    @State private var selection = LeaderboardSelection(stageKey: "regular_season", teamSectionKey: "S")

    var body: some View {
        ScrollView {
            HomeLeaderboardView(payload: Self.payload, selection: $selection) { _ in }
                .padding()
        }
        .pageBackground()
    }

    private static let payload: DashboardResponse = {
        let json = #"{"leaderboard_stages":[{"key":"all","label":"全部"},{"key":"regular_season","label":"常规赛"}],"leaderboards":{},"leaderboards_by_stage":{"regular_season":{"players":[],"mvp":[],"svp":[]}},"team_leaderboard_sections":{"regular_season":[{"key":"S","label":"S组","title":"S组常规赛榜","rows":[{"rank":1,"team_id":"team-s","name":"洵岛","points_total":"32.50","win_rate":"58.3%","matches_represented":12,"badges":[{"text":"直通","style":"orange","kind":"progress"}]}]},{"key":"F","label":"F组","title":"F组常规赛榜","rows":[{"rank":1,"team_id":"team-f","name":"灌狼高手","points_total":"23.00","win_rate":"54.2%","matches_represented":12,"badges":[{"text":"晋级","style":"green","kind":"progress"}]}]}]}}"#
        return try! JSONDecoder().decode(DashboardResponse.self, from: Data(json.utf8))
    }()
}

#Preview("分组排行榜") {
    HomeLeaderboardPreview()
}

#Preview("深色与大字体") {
    HomeLeaderboardPreview()
        .preferredColorScheme(.dark)
        .environment(\.dynamicTypeSize, .accessibility2)
}
#endif
