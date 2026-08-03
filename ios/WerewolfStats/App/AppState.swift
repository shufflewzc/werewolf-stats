import Foundation
import Observation

@MainActor
@Observable
final class AppState {
    static let scopeKey = "werewolf.selectedCompetitionScope"
    static let favoritesKey = "werewolf.favoritePlayerIDs"

    let api: APIClient
    let tabRouter = TabRouter()
    var selectedTab: AppTab = .home
    var selectedScope: CompetitionScope? {
        didSet { persistScope() }
    }
    private(set) var favoritePlayerIDs: Set<String> {
        didSet { persistFavorites() }
    }

    private let defaults: UserDefaults

    init(
        api: APIClient = APIClient(),
        defaults: UserDefaults = .standard,
        arguments: [String] = ProcessInfo.processInfo.arguments
    ) {
        self.api = api
        self.defaults = defaults
        if arguments.contains("-resetUserDefaults") {
            defaults.removeObject(forKey: Self.scopeKey)
            defaults.removeObject(forKey: Self.favoritesKey)
        }
        if let data = defaults.data(forKey: Self.scopeKey),
           let scope = try? JSONDecoder().decode(CompetitionScope.self, from: data) {
            self.selectedScope = scope
        } else {
            self.selectedScope = nil
        }
        self.favoritePlayerIDs = Set(defaults.stringArray(forKey: Self.favoritesKey) ?? [])
    }

    func select(_ scope: CompetitionScope) {
        selectedScope = scope
        selectedTab = .home
        tabRouter.router(for: .home).reset()
    }

    func isFavorite(_ playerID: String) -> Bool {
        favoritePlayerIDs.contains(playerID)
    }

    func toggleFavorite(_ playerID: String) {
        if favoritePlayerIDs.contains(playerID) { favoritePlayerIDs.remove(playerID) }
        else { favoritePlayerIDs.insert(playerID) }
    }

    @discardableResult
    func handleDeepLink(_ url: URL) -> Bool {
        guard url.host == api.baseURL.host else { return false }
        if let scope = Self.scope(from: url) { selectedScope = scope }
        let parts = url.pathComponents.filter { $0 != "/" }
        guard let root = parts.first else { return false }

        let route: AppRoute?
        let tab: AppTab
        switch root {
        case "players" where parts.count > 1:
            tab = .players; route = .player(parts[1])
        case "teams" where parts.count > 1:
            tab = .home; route = .team(parts[1])
        case "matches" where parts.count > 1:
            tab = .home; route = .match(parts[1])
        case "days" where parts.count > 1:
            tab = .home; route = .day(parts[1])
        case "guilds" where parts.count > 1:
            tab = .guilds; route = .guild(parts[1])
        case "guilds":
            tab = .guilds; route = nil
        case "competitions":
            tab = .competitions; route = nil
        default: return false
        }
        selectedTab = tab
        let router = tabRouter.router(for: tab)
        router.reset()
        if let route { router.navigate(to: route) }
        return true
    }

    private func persistScope() {
        guard let selectedScope, let data = try? JSONEncoder().encode(selectedScope) else {
            defaults.removeObject(forKey: Self.scopeKey)
            return
        }
        defaults.set(data, forKey: Self.scopeKey)
    }

    private func persistFavorites() {
        defaults.set(favoritePlayerIDs.sorted(), forKey: Self.favoritesKey)
    }

    private static func scope(from url: URL) -> CompetitionScope? {
        guard let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return nil }
        let values = Dictionary(uniqueKeysWithValues: items.compactMap { item in item.value.map { (item.name, $0) } })
        guard let competition = values["competition"], !competition.isEmpty else { return nil }
        return CompetitionScope(
            competition: competition,
            season: values["season"] ?? "",
            region: values["region"] ?? "",
            series: values["series"] ?? "",
            seriesName: ""
        )
    }
}
