import SwiftUI

@main
struct WerewolfStatsApp: App {
    @State private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            AppView()
                .environment(appState)
                .tint(Brand.gold)
                .onOpenURL { _ = appState.handleDeepLink($0) }
        }
    }
}

struct AppView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        @Bindable var app = app
        TabView(selection: $app.selectedTab) {
            tab(.home) { HomeView() }
            tab(.competitions) { CompetitionsView() }
            tab(.guilds) { GuildsView() }
            tab(.players) { PlayersView() }
        }
        .accessibilityIdentifier("main-tab-view")
    }

    private func tab<Content: View>(_ tab: AppTab, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack(path: app.tabRouter.binding(for: tab)) {
            content()
                .appDestinations()
        }
        .environment(app.tabRouter.router(for: tab))
        .tabItem { Label(tab.title, systemImage: tab.systemImage) }
        .tag(tab)
    }
}
