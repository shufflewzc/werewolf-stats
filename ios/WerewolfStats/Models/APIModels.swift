import Foundation

private extension KeyedDecodingContainer {
    func decodeLossyIntIfPresent(forKey key: Key) -> Int? {
        if let value = try? decodeIfPresent(Int.self, forKey: key) { return value }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return Int(value) ?? Double(value).map(Int.init)
        }
        if let value = try? decodeIfPresent(Double.self, forKey: key) { return Int(value) }
        return nil
    }
}

enum LoadState<Value> {
    case idle
    case loading
    case loaded(Value, isStale: Bool)
    case failed(String)
}

enum JSONScalar: Codable, Hashable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else { throw DecodingError.typeMismatch(JSONScalar.self, .init(codingPath: decoder.codingPath, debugDescription: "Unsupported scalar")) }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var text: String {
        switch self {
        case .string(let value): value
        case .number(let value): value.rounded() == value ? String(Int(value)) : String(format: "%.2f", value)
        case .bool(let value): value ? "是" : "否"
        case .null: "--"
        }
    }
}

struct APIResult<Value: Sendable>: Sendable {
    let value: Value
    let isStale: Bool
}

struct CompetitionScope: Codable, Hashable, Sendable {
    let competition: String
    let season: String
    let region: String
    let series: String
    let seriesName: String

    var queryItems: [URLQueryItem] {
        [
            URLQueryItem(name: "competition", value: competition),
            URLQueryItem(name: "season", value: season),
            URLQueryItem(name: "region", value: region),
            URLQueryItem(name: "series", value: series)
        ].filter { !($0.value ?? "").isEmpty }
    }

    var subtitle: String {
        [region, seriesName, season].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

struct Metric: Codable, Hashable, Identifiable, Sendable {
    let label: String
    let value: JSONScalar
    let copy: String?
    var id: String { label }
}

struct Hero: Codable, Hashable, Sendable {
    let title: String?
    let label: String?
    let eyebrow: String?
    let copy: String?
    let description: String?
    let featuredLabel: String?

    enum CodingKeys: String, CodingKey {
        case title, label, eyebrow, copy, description
        case featuredLabel = "featured_label"
    }
}

struct Pagination: Codable, Hashable, Sendable {
    let offset: Int
    let limit: Int
    let total: Int
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case offset, limit, total
        case hasMore = "has_more"
    }
}

struct PowerRating: Codable, Hashable, Sendable {
    let grade: String?
    let score: Double?
    let sourceLabel: String?
    enum CodingKeys: String, CodingKey {
        case grade, score
        case sourceLabel = "source_label"
    }
}

struct CompetitionResponse: Codable, Sendable {
    let generatedAt: String?
    let hero: Hero?
    let metrics: [Metric]?
    let cards: [CompetitionCard]
    enum CodingKeys: String, CodingKey {
        case hero, metrics, cards
        case generatedAt = "generated_at"
    }
}

struct CompetitionCard: Codable, Hashable, Identifiable, Sendable {
    let competitionName: String
    let regionName: String
    let seriesName: String
    let summary: String?
    let seasons: [String]
    let latestPlayedOn: String?
    let teamCount: Int?
    let playerCount: Int?
    let matchCount: Int?
    let seasonStats: [String: SeasonStats]?
    let competitionHref: String?

    var id: String { competitionName }

    enum CodingKeys: String, CodingKey {
        case summary, seasons
        case competitionName = "competition_name"
        case regionName = "region_name"
        case seriesName = "series_name"
        case latestPlayedOn = "latest_played_on"
        case teamCount = "team_count"
        case playerCount = "player_count"
        case matchCount = "match_count"
        case seasonStats = "season_stats"
        case competitionHref = "competition_href"
    }

    func scope(for season: String) -> CompetitionScope {
        let components = competitionHref.flatMap { URLComponents(string: $0) }
        let series = components?.queryItems?.first(where: { $0.name == "series" })?.value ?? ""
        return CompetitionScope(competition: competitionName, season: season, region: regionName, series: series, seriesName: seriesName)
    }
}

struct SeasonStats: Codable, Hashable, Sendable {
    let matchCount: Int?
    let teamCount: Int?
    let playerCount: Int?
    let latestPlayedOn: String?
    enum CodingKeys: String, CodingKey {
        case matchCount = "match_count"
        case teamCount = "team_count"
        case playerCount = "player_count"
        case latestPlayedOn = "latest_played_on"
    }
}

struct DashboardResponse: Codable, Sendable {
    let generatedAt: String?
    let hero: Hero?
    let metrics: [Metric]?
    let topTeams: [TeamSummary]?
    let topPlayers: [PlayerSummary]?
    let matchDays: [MatchDaySummary]?
    let scheduleMatches: [ScheduleMatch]?
    let leaderboards: [String: [LeaderboardRow]]?
    let leaderboardStages: [LeaderboardStage]?
    let leaderboardsByStage: [String: [String: [LeaderboardRow]]]?
    let teamLeaderboardSections: [String: [TeamLeaderboardSection]]?
    let regularSeasonTeamLeaderboards: [String: [LeaderboardRow]]?

    enum CodingKeys: String, CodingKey {
        case hero, metrics, leaderboards
        case generatedAt = "generated_at"
        case topTeams = "top_teams"
        case topPlayers = "top_players"
        case matchDays = "match_days"
        case scheduleMatches = "schedule_matches"
        case leaderboardStages = "leaderboard_stages"
        case leaderboardsByStage = "leaderboards_by_stage"
        case teamLeaderboardSections = "team_leaderboard_sections"
        case regularSeasonTeamLeaderboards = "regular_season_team_leaderboards"
    }
}

struct LeaderboardStage: Codable, Hashable, Identifiable, Sendable {
    let key: String
    let label: String
    var id: String { key }
}

struct TeamLeaderboardSection: Codable, Hashable, Identifiable, Sendable {
    let key: String
    let label: String
    let title: String
    let rows: [LeaderboardRow]

    var id: String { key }
}

struct LeaderboardBadge: Codable, Hashable, Sendable {
    let text: String
    let style: String?
    let kind: String?

    init(text: String, style: String? = nil, kind: String? = nil) {
        self.text = text
        self.style = style
        self.kind = kind
    }
}

struct LeaderboardRow: Codable, Hashable, Identifiable, Sendable {
    let rank: Int?
    let teamID: String?
    let playerID: String?
    let name: String?
    let shortName: String?
    let displayName: String?
    let teamName: String?
    let pointsTotal: JSONScalar?
    let winRate: String?
    let matchesRepresented: Int?
    let gamesPlayed: Int?
    let awardCount: Int?
    let awardLabel: String?
    let latestAwardedOn: String?
    let regularSeasonGroup: String?
    let groupLabel: String?
    let progressStatus: String?
    let badges: [LeaderboardBadge]?
    let isStarPlayer: Bool?

    var id: String { teamID ?? playerID ?? "\(rank ?? 0)-\(title)" }
    var title: String { shortName ?? name ?? displayName ?? teamName ?? "未知" }
    var valueText: String { pointsTotal?.text ?? awardCount.map(String.init) ?? "--" }
    var isTeam: Bool { teamID != nil }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        rank = container.decodeLossyIntIfPresent(forKey: .rank)
        teamID = try container.decodeIfPresent(String.self, forKey: .teamID)
        playerID = try container.decodeIfPresent(String.self, forKey: .playerID)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        shortName = try container.decodeIfPresent(String.self, forKey: .shortName)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        teamName = try container.decodeIfPresent(String.self, forKey: .teamName)
        pointsTotal = try container.decodeIfPresent(JSONScalar.self, forKey: .pointsTotal)
        winRate = try container.decodeIfPresent(String.self, forKey: .winRate)
        matchesRepresented = container.decodeLossyIntIfPresent(forKey: .matchesRepresented)
        gamesPlayed = container.decodeLossyIntIfPresent(forKey: .gamesPlayed)
        awardCount = container.decodeLossyIntIfPresent(forKey: .awardCount)
        awardLabel = try container.decodeIfPresent(String.self, forKey: .awardLabel)
        latestAwardedOn = try container.decodeIfPresent(String.self, forKey: .latestAwardedOn)
        regularSeasonGroup = try container.decodeIfPresent(String.self, forKey: .regularSeasonGroup)
        groupLabel = try container.decodeIfPresent(String.self, forKey: .groupLabel)
        progressStatus = try container.decodeIfPresent(String.self, forKey: .progressStatus)
        badges = try container.decodeIfPresent([LeaderboardBadge].self, forKey: .badges)
        isStarPlayer = try container.decodeIfPresent(Bool.self, forKey: .isStarPlayer)
    }

    enum CodingKeys: String, CodingKey {
        case rank, name
        case teamID = "team_id"
        case playerID = "player_id"
        case shortName = "short_name"
        case displayName = "display_name"
        case teamName = "team_name"
        case pointsTotal = "points_total"
        case winRate = "win_rate"
        case matchesRepresented = "matches_represented"
        case gamesPlayed = "games_played"
        case awardCount = "award_count"
        case awardLabel = "award_label"
        case latestAwardedOn = "latest_awarded_on"
        case regularSeasonGroup = "regular_season_group"
        case groupLabel = "group_label"
        case progressStatus = "progress_status"
        case badges
        case isStarPlayer = "is_star_player"
    }
}

struct MatchDaySummary: Codable, Hashable, Identifiable, Sendable {
    let playedOn: String
    let matchCount: Int
    let competitionNames: [String]?
    var id: String { playedOn }
    enum CodingKeys: String, CodingKey {
        case playedOn = "played_on"
        case matchCount = "match_count"
        case competitionNames = "competition_names"
    }
}

struct ScheduleMatch: Codable, Hashable, Identifiable, Sendable {
    let matchID: String
    let playedOn: String?
    let stage: String?
    let round: Int?
    let gameNo: Int?
    let tableLabel: String?
    var id: String { matchID }
    enum CodingKeys: String, CodingKey {
        case stage, round
        case matchID = "match_id"
        case playedOn = "played_on"
        case gameNo = "game_no"
        case tableLabel = "table_label"
    }
}

struct GuildsResponse: Codable, Sendable {
    let hero: Hero?
    let metrics: [Metric]?
    let cards: [GuildCard]
}

struct GuildCard: Codable, Hashable, Identifiable, Sendable {
    let guildID: String
    let name: String
    let shortName: String?
    let notes: String?
    let teamCount: Int?
    let ongoingTeamCount: Int?
    let matchCount: Int?
    let honorCount: Int?
    var id: String { guildID }
    enum CodingKeys: String, CodingKey {
        case name, notes
        case guildID = "guild_id"
        case shortName = "short_name"
        case teamCount = "team_count"
        case ongoingTeamCount = "ongoing_team_count"
        case matchCount = "match_count"
        case honorCount = "honor_count"
    }
}

struct GuildDetailResponse: Codable, Sendable {
    let guild: GuildCard
    let metrics: [Metric]?
    let honors: [GuildHonor]?
    let ongoingTeams: [GuildTeam]?
    let historySections: [GuildHistorySection]?
    enum CodingKeys: String, CodingKey {
        case guild, metrics, honors
        case ongoingTeams = "ongoing_teams"
        case historySections = "history_sections"
    }
}

struct GuildHonor: Codable, Hashable, Identifiable, Sendable {
    let title: String
    let teamName: String?
    let scope: String?
    var id: String { "\(title)-\(teamName ?? "")-\(scope ?? "")" }
    enum CodingKeys: String, CodingKey { case title, scope; case teamName = "team_name" }
}

struct GuildTeam: Codable, Hashable, Identifiable, Sendable {
    let teamID: String
    let teamName: String
    let competitionName: String?
    let seasonName: String?
    let statusLabel: String?
    let matches: Int?
    let playerCount: Int?
    let pointsTotal: JSONScalar?
    var id: String { teamID }
    enum CodingKeys: String, CodingKey {
        case matches
        case teamID = "team_id"
        case teamName = "team_name"
        case competitionName = "competition_name"
        case seasonName = "season_name"
        case statusLabel = "status_label"
        case playerCount = "player_count"
        case pointsTotal = "points_total"
    }
}

struct GuildHistorySection: Codable, Hashable, Identifiable, Sendable {
    let competitionName: String
    let rows: [GuildTeam]
    var id: String { competitionName }
    enum CodingKeys: String, CodingKey { case rows; case competitionName = "competition_name" }
}

struct PlayersResponse: Codable, Sendable {
    let generatedAt: String?
    let metrics: [Metric]?
    let players: [PlayerSummary]
    let pagination: Pagination?
    let requiresScope: Bool?
    enum CodingKeys: String, CodingKey {
        case metrics, players, pagination
        case generatedAt = "generated_at"
        case requiresScope = "requires_scope"
    }
}

struct PlayerSummary: Codable, Hashable, Identifiable, Sendable {
    let rank: Int?
    let playerID: String
    let displayName: String
    let isStarPlayer: Bool?
    let teamName: String?
    let photo: String?
    let gamesPlayed: Int?
    let pointsTotal: JSONScalar?
    let winRate: String?
    let powerRating: PowerRating?
    var id: String { playerID }
    enum CodingKeys: String, CodingKey {
        case rank, photo
        case playerID = "player_id"
        case displayName = "display_name"
        case isStarPlayer = "is_star_player"
        case teamName = "team_name"
        case gamesPlayed = "games_played"
        case pointsTotal = "points_total"
        case winRate = "win_rate"
        case powerRating = "power_rating"
    }
}

struct PlayerDetailResponse: Codable, Sendable {
    let player: PlayerDetail
    let metrics: [Metric]?
    let insights: PlayerInsights?
    let roles: [RoleStat]?
    let recentMatches: [RecentMatch]?
    let achievements: [Achievement]?
    let dimension: PlayerDimension?
    enum CodingKeys: String, CodingKey {
        case player, metrics, insights, roles, achievements, dimension
        case recentMatches = "recent_matches"
    }
}

struct PlayerDetail: Codable, Hashable, Sendable {
    let playerID: String
    let name: String
    let photo: String?
    let teamName: String?
    let rank: Int?
    let owner: String?
    let isStarPlayer: Bool?
    let powerRating: PowerRating?
    enum CodingKeys: String, CodingKey {
        case name, photo, rank, owner
        case playerID = "player_id"
        case teamName = "team_name"
        case isStarPlayer = "is_star_player"
        case powerRating = "power_rating"
    }
}

struct PlayerInsights: Codable, Hashable, Sendable {
    let overallWinRate: String?
    let villagersWinRate: String?
    let werewolvesWinRate: String?
    let mvpCount: Int?
    enum CodingKeys: String, CodingKey {
        case overallWinRate = "overall_win_rate"
        case villagersWinRate = "villagers_win_rate"
        case werewolvesWinRate = "werewolves_win_rate"
        case mvpCount = "mvp_count"
    }
}

struct RoleStat: Codable, Hashable, Identifiable, Sendable {
    let role: String
    let games: Int?
    let share: String?
    let width: Double?
    var id: String { role }
}

struct RecentMatch: Codable, Hashable, Identifiable, Sendable {
    let matchID: String
    let playedOn: String?
    let round: Int?
    let gameNo: Int?
    let role: String?
    let resultLabel: String?
    let pointsEarned: JSONScalar?
    var id: String { matchID }
    enum CodingKeys: String, CodingKey {
        case round, role
        case matchID = "match_id"
        case playedOn = "played_on"
        case gameNo = "game_no"
        case resultLabel = "result_label"
        case pointsEarned = "points_earned"
    }
}

struct Achievement: Codable, Hashable, Identifiable, Sendable {
    let code: String
    let title: String
    let meta: String?
    let description: String?
    let tier: String?
    var id: String { code }
}

struct PlayerDimension: Codable, Hashable, Sendable {
    let available: Bool?
    let reason: String?
    let selectedSeason: String?
    let summaryCards: [Metric]?
    let radar: [DimensionRadar]?
    let history: [DimensionHistory]?
    enum CodingKeys: String, CodingKey {
        case available, reason, radar, history
        case selectedSeason = "selected_season"
        case summaryCards = "summary_cards"
    }
}

struct DimensionRadar: Codable, Hashable, Identifiable, Sendable {
    let label: String
    let display: String?
    let ratio: Double?
    var id: String { label }
}

struct DimensionHistory: Codable, Hashable, Identifiable, Sendable {
    let playedOn: String
    let teamName: String?
    let seat: Int?
    let gamesPlayed: Int?
    let wins: Int?
    let dailyPoints: JSONScalar?
    var id: String { "\(playedOn)-\(seat ?? 0)" }
    enum CodingKeys: String, CodingKey {
        case seat, wins
        case playedOn = "played_on"
        case teamName = "team_name"
        case gamesPlayed = "games_played"
        case dailyPoints = "daily_points"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        playedOn = try container.decode(String.self, forKey: .playedOn)
        teamName = try container.decodeIfPresent(String.self, forKey: .teamName)
        seat = container.decodeLossyIntIfPresent(forKey: .seat)
        gamesPlayed = container.decodeLossyIntIfPresent(forKey: .gamesPlayed)
        wins = container.decodeLossyIntIfPresent(forKey: .wins)
        dailyPoints = try container.decodeIfPresent(JSONScalar.self, forKey: .dailyPoints)
    }
}

struct TeamsResponse: Codable, Sendable {
    let metrics: [Metric]?
    let teams: [TeamSummary]
}

struct TeamSummary: Codable, Hashable, Identifiable, Sendable {
    let rank: Int?
    let teamID: String
    let name: String
    let shortName: String?
    let logo: String?
    let playerCount: Int?
    let matchesRepresented: Int?
    let pointsTotal: JSONScalar?
    let winRate: String?
    let powerRating: PowerRating?
    var id: String { teamID }
    enum CodingKeys: String, CodingKey {
        case rank, name, logo
        case teamID = "team_id"
        case shortName = "short_name"
        case playerCount = "player_count"
        case matchesRepresented = "matches_represented"
        case pointsTotal = "points_total"
        case winRate = "win_rate"
        case powerRating = "power_rating"
    }
}

struct TeamDetailResponse: Codable, Sendable {
    let team: TeamDetail
    let metrics: [Metric]?
    let achievements: [Achievement]?
    let roster: [RosterMember]?
    let matches: [TeamMatch]?
}

struct TeamDetail: Codable, Hashable, Sendable {
    let teamID: String
    let name: String
    let shortName: String?
    let logo: String?
    let notes: String?
    let statusLabel: String?
    let captain: String?
    let guild: String?
    let powerRating: PowerRating?
    enum CodingKeys: String, CodingKey {
        case name, logo, notes, captain, guild
        case teamID = "team_id"
        case shortName = "short_name"
        case statusLabel = "status_label"
        case powerRating = "power_rating"
    }
}

struct RosterMember: Codable, Hashable, Identifiable, Sendable {
    let playerID: String
    let displayName: String?
    let name: String?
    let photo: String?
    let matches: Int?
    let points: JSONScalar?
    let winRate: String?
    let topRole: String?
    var id: String { playerID }
    var title: String { displayName ?? name ?? playerID }
    enum CodingKeys: String, CodingKey {
        case name, photo
        case playerID = "player_id"
        case displayName = "display_name"
        case matches, points
        case winRate = "win_rate"
        case topRole = "top_role"
    }
}

struct TeamMatch: Codable, Hashable, Identifiable, Sendable {
    let matchID: String
    let playedOn: String?
    let round: Int?
    let gameNo: Int?
    let points: JSONScalar?
    let result: String?
    let stageLabel: String?
    var id: String { matchID }
    enum CodingKeys: String, CodingKey {
        case round, points, result
        case matchID = "match_id"
        case playedOn = "played_on"
        case gameNo = "game_no"
        case stageLabel = "stage_label"
    }
}

struct MatchDetailResponse: Codable, Sendable {
    let match: MatchDetail
    let metrics: [Metric]?
    let awards: [MatchAward]?
    let teamScores: [MatchTeamScore]?
    let scorePredictions: [MatchPrediction]?
    let participants: [MatchParticipant]?
    enum CodingKeys: String, CodingKey {
        case match, metrics, awards, participants
        case teamScores = "team_scores"
        case scorePredictions = "score_predictions"
    }
}

struct MatchDetail: Codable, Hashable, Sendable {
    let matchID: String
    let competition: String?
    let season: String?
    let stage: String?
    let round: Int?
    let gameNo: Int?
    let playedOn: String?
    let tableLabel: String?
    let format: String?
    let durationMinutes: Int?
    let winningCamp: String?
    let notes: String?
    enum CodingKeys: String, CodingKey {
        case competition, season, stage, round, format, notes
        case matchID = "match_id"
        case gameNo = "game_no"
        case playedOn = "played_on"
        case tableLabel = "table_label"
        case durationMinutes = "duration_minutes"
        case winningCamp = "winning_camp"
    }
}

struct MatchAward: Codable, Hashable, Identifiable, Sendable {
    let label: String
    let playerID: String?
    let playerName: String?
    let meta: String?
    var id: String { label }
    enum CodingKeys: String, CodingKey { case label, meta; case playerID = "player_id"; case playerName = "player_name" }
}

struct MatchTeamScore: Codable, Hashable, Identifiable, Sendable {
    let teamID: String
    let teamName: String
    let points: JSONScalar?
    let groupLabel: String?
    var id: String { teamID }
    enum CodingKeys: String, CodingKey { case points; case teamID = "team_id"; case teamName = "team_name"; case groupLabel = "group_label" }
}

struct MatchParticipant: Codable, Hashable, Identifiable, Sendable {
    let seat: Int
    let playerID: String
    let playerName: String
    let teamName: String?
    let role: String?
    let camp: String?
    let result: String?
    let points: JSONScalar?
    var id: String { playerID }
    enum CodingKeys: String, CodingKey { case seat, role, camp, result, points; case playerID = "player_id"; case playerName = "player_name"; case teamName = "team_name" }
}

struct MatchPrediction: Codable, Hashable, Identifiable, Sendable {
    let playerID: String
    let playerName: String
    let teamName: String?
    let expectedPoints: JSONScalar?
    let expectedWinRate: String?
    let confidence: String?
    var id: String { playerID }
    enum CodingKeys: String, CodingKey {
        case confidence
        case playerID = "player_id"
        case playerName = "player_name"
        case teamName = "team_name"
        case expectedPoints = "expected_points"
        case expectedWinRate = "expected_win_rate"
    }
}

struct DayDetailResponse: Codable, Sendable {
    let hero: Hero?
    let metrics: [Metric]?
    let aiReport: AIReport?
    let teamLeaderboard: [LeaderboardRow]?
    let playerLeaderboard: [LeaderboardRow]?
    let competitions: [DayCompetition]?
    enum CodingKeys: String, CodingKey {
        case hero, metrics, competitions
        case aiReport = "ai_report"
        case teamLeaderboard = "team_leaderboard"
        case playerLeaderboard = "player_leaderboard"
    }
}

struct AIReport: Codable, Hashable, Sendable {
    let exists: Bool?
    let generatedAt: String?
    let content: String?
    let emptyCopy: String?
    enum CodingKeys: String, CodingKey { case exists, content; case generatedAt = "generated_at"; case emptyCopy = "empty_copy" }
}

struct DayCompetition: Codable, Hashable, Identifiable, Sendable {
    let competitionName: String
    let matches: [ScheduleMatch]?
    var id: String { competitionName }
    enum CodingKeys: String, CodingKey { case matches; case competitionName = "competition_name" }
}

struct PredictionsResponse: Codable, Sendable {
    let generatedAt: String?
    let days: [PredictionDay]?
    let selectedDay: PredictionDay?
    let predictions: [Prediction]
    let pagination: Pagination?
    let bandSummary: [PredictionBand]?
    let notice: String?
    enum CodingKeys: String, CodingKey {
        case days, predictions, pagination, notice
        case generatedAt = "generated_at"
        case selectedDay = "selected_day"
        case bandSummary = "band_summary"
    }
}

struct PredictionDay: Codable, Hashable, Identifiable, Sendable {
    let playedOn: String
    let matchCount: Int?
    var id: String { playedOn }
    enum CodingKeys: String, CodingKey { case playedOn = "played_on"; case matchCount = "match_count" }
}

struct Prediction: Codable, Hashable, Identifiable, Sendable {
    let rank: Int?
    let playerID: String
    let playerName: String
    let teamName: String?
    let winRate: String?
    let confidence: String?
    let matchCount: Int?
    let expectedTotal: JSONScalar?
    let expectedPoints: JSONScalar?
    let matchLabels: [String]?
    var id: String { playerID }
    var scoreText: String { expectedTotal?.text ?? expectedPoints?.text ?? "--" }
    enum CodingKeys: String, CodingKey {
        case rank, confidence
        case playerID = "player_id"
        case playerName = "player_name"
        case teamName = "team_name"
        case winRate = "win_rate"
        case matchCount = "match_count"
        case expectedTotal = "expected_total"
        case expectedPoints = "expected_points"
        case matchLabels = "match_labels"
    }
}

struct PredictionBand: Codable, Hashable, Identifiable, Sendable {
    let label: String
    let copy: String?
    let value: JSONScalar?
    var id: String { label }
}

struct SearchResponse: Codable, Sendable {
    let keyword: String?
    let results: [SearchResult]
}

struct SearchResult: Codable, Hashable, Identifiable, Sendable {
    let key: String
    let type: String
    let typeLabel: String?
    let entityID: String
    let title: String
    let subtitle: String?
    let isStarPlayer: Bool?
    var id: String { key }
    enum CodingKeys: String, CodingKey {
        case key, type, title, subtitle
        case typeLabel = "type_label"
        case entityID = "id"
        case isStarPlayer = "is_star_player"
    }
}
