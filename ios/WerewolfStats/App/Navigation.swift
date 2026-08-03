import Observation
import SwiftUI

enum AppTab: String, CaseIterable, Identifiable, Hashable {
    case home, competitions, guilds, players
    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: "首页"
        case .competitions: "赛事"
        case .guilds: "门派"
        case .players: "选手"
        }
    }

    var systemImage: String {
        switch self {
        case .home: "house.fill"
        case .competitions: "trophy.fill"
        case .guilds: "shield.lefthalf.filled"
        case .players: "person.3.fill"
        }
    }
}

enum EntityKind: String, Hashable { case player, team }
enum ShareCardOrientation: String, CaseIterable, Identifiable { case portrait, landscape; var id: String { rawValue } }

enum AppRoute: Hashable {
    case player(String)
    case team(String)
    case match(String)
    case day(String)
    case guild(String)
    case predictions(playedOn: String?, matchID: String?)
    case compare(kind: EntityKind, leftID: String?)
    case share(playerID: String)
}

@MainActor
@Observable
final class RouterPath {
    var path: [AppRoute] = []
    func navigate(to route: AppRoute) { path.append(route) }
    func reset() { path.removeAll() }
}

@MainActor
@Observable
final class TabRouter {
    private var routers: [AppTab: RouterPath] = [:]

    func router(for tab: AppTab) -> RouterPath {
        if let router = routers[tab] { return router }
        let router = RouterPath()
        routers[tab] = router
        return router
    }

    func binding(for tab: AppTab) -> Binding<[AppRoute]> {
        let router = router(for: tab)
        return Binding(get: { router.path }, set: { router.path = $0 })
    }
}

struct AppDestinations: ViewModifier {
    func body(content: Content) -> some View {
        content.navigationDestination(for: AppRoute.self) { route in
            switch route {
            case .player(let id): PlayerDetailView(playerID: id)
            case .team(let id): TeamDetailView(teamID: id)
            case .match(let id): MatchDetailView(matchID: id)
            case .day(let date): DayDetailView(playedOn: date)
            case .guild(let id): GuildDetailView(guildID: id)
            case .predictions(let playedOn, let matchID): PredictionsView(initialDay: playedOn, initialMatchID: matchID)
            case .compare(let kind, let leftID): CompareView(kind: kind, initialLeftID: leftID)
            case .share(let playerID): ShareCardView(playerID: playerID)
            }
        }
    }
}

extension View {
    func appDestinations() -> some View { modifier(AppDestinations()) }
}
