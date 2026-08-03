import Photos
import SwiftUI
import UIKit

private struct ActivityItems: Identifiable {
    let id = UUID()
    let items: [Any]
}

private struct ActivitySheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct ShareCardView: View {
    @Environment(AppState.self) private var app
    let playerID: String
    @State private var state: LoadState<PlayerDetailResponse> = .idle
    @State private var orientation: ShareCardOrientation = .portrait
    @State private var selectedAchievements: Set<String> = []
    @State private var avatar: UIImage?
    @State private var qrImage: UIImage?
    @State private var renderedImage: UIImage?
    @State private var activityItems: ActivityItems?
    @State private var alertMessage: String?

    var body: some View {
        Group {
            if app.selectedScope == nil { ScopeRequiredView() }
            else { switch state {
            case .idle, .loading: LoadingContent(label: "正在生成战绩卡")
            case .failed(let message): ErrorContent(message: message) { Task { await load(force: true) } }
            case .loaded(let payload, _): editor(payload)
            } }
        }
        .navigationTitle("战绩卡").navigationBarTitleDisplayMode(.inline)
        .sheet(item: $activityItems) { ActivitySheet(items: $0.items) }
        .alert("战绩卡", isPresented: Binding(get: { alertMessage != nil }, set: { if !$0 { alertMessage = nil } })) { Button("知道了", role: .cancel) {} } message: { Text(alertMessage ?? "") }
        .task(id: app.selectedScope) { await load() }
        .onChange(of: orientation) { _, _ in render() }
        .onChange(of: selectedAchievements) { _, _ in render() }
    }

    private func editor(_ payload: PlayerDetailResponse) -> some View {
        ScrollView {
            VStack(spacing: 16) {
                Picker("版式", selection: $orientation) { Text("竖版").tag(ShareCardOrientation.portrait); Text("横版").tag(ShareCardOrientation.landscape) }.pickerStyle(.segmented)
                if let image = renderedImage {
                    Image(uiImage: image).resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius: 14)).shadow(radius: 8, y: 4).accessibilityLabel("\(payload.player.name)的战绩卡预览").accessibilityIdentifier("share-card-preview")
                } else { ProgressView("正在渲染战绩卡").frame(maxWidth: .infinity, minHeight: 300) }
                achievementPicker(payload.achievements ?? [])
                HStack {
                    Button("系统分享", systemImage: "square.and.arrow.up") { share() }.buttonStyle(.borderedProminent).disabled(renderedImage == nil)
                    Button("保存相册", systemImage: "square.and.arrow.down") { save() }.buttonStyle(.bordered).disabled(renderedImage == nil)
                }
                Text("微信扫码后进入对应选手的小程序详情。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .accessibilityIdentifier("share-qr-mini-program-note")
            }.padding()
        }.pageBackground()
    }

    @ViewBuilder private func achievementPicker(_ achievements: [Achievement]) -> some View {
        if !achievements.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "卡片成就", note: "最多 2 个")
                FlowLayout(spacing: 8) {
                    ForEach(achievements.prefix(6)) { item in
                        Button {
                            if selectedAchievements.contains(item.code) { selectedAchievements.remove(item.code) }
                            else if selectedAchievements.count < 2 { selectedAchievements.insert(item.code) }
                            else { alertMessage = "战绩卡最多展示两个成就。" }
                        } label: { Label(item.title, systemImage: selectedAchievements.contains(item.code) ? "checkmark.circle.fill" : "circle").font(.caption).padding(.horizontal, 10).padding(.vertical, 7).background(selectedAchievements.contains(item.code) ? Brand.paleGold : Brand.card, in: Capsule()) }.buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }; state = .loading
        do {
            let result = try await app.api.get("/api/players/\(playerID)", queryItems: scope.queryItems + [URLQueryItem(name: "strict_player_id", value: "1")], as: PlayerDetailResponse.self, forceRefresh: force)
            selectedAchievements = Set((result.value.achievements ?? []).prefix(2).map(\.code))
            state = .loaded(result.value, isStale: result.isStale)
            if let url = app.api.assetURL(result.value.player.photo), let data = try? await app.api.remoteData(from: url) { avatar = UIImage(data: data) }
            await loadMiniProgramCodeAndRender()
        } catch is CancellationError { return } catch { state = .failed(error.localizedDescription) }
    }

    private func loadMiniProgramCodeAndRender() async {
        guard case .loaded = state else { return }
        do {
            let data = try await app.api.imageData("/api/miniprogram/share-code", queryItems: [URLQueryItem(name: "player_id", value: playerID)])
            qrImage = UIImage(data: data)
        } catch {
            qrImage = nil
            alertMessage = "小程序码加载失败，请稍后重试。"
        }
        render()
    }

    @MainActor private func render() {
        guard case .loaded(let payload, _) = state else { return }
        let selected = (payload.achievements ?? []).filter { selectedAchievements.contains($0.code) }
        let size = orientation == .portrait ? CGSize(width: 362, height: 482.67) : CGSize(width: 482.67, height: 362)
        let card = PlayerPerformanceCard(payload: payload, scope: app.selectedScope!, avatar: avatar, qrImage: qrImage, achievements: Array(selected.prefix(2)), orientation: orientation)
        let renderer = ImageRenderer(content: card.frame(width: size.width, height: size.height))
        renderer.scale = 3
        renderer.isOpaque = true
        renderedImage = renderer.uiImage
    }

    private func share() {
        guard let renderedImage else { return }
        activityItems = ActivityItems(items: [renderedImage])
    }

    private func save() {
        guard let renderedImage else { return }
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            Task { @MainActor in
                guard status == .authorized || status == .limited else { alertMessage = "请在系统设置中允许添加照片后重试。"; return }
                UIImageWriteToSavedPhotosAlbum(renderedImage, nil, nil, nil)
                alertMessage = "战绩卡已保存到照片图库。"
            }
        }
    }

}

private struct PlayerPerformanceCard: View {
    let payload: PlayerDetailResponse
    let scope: CompetitionScope
    let avatar: UIImage?
    let qrImage: UIImage?
    let achievements: [Achievement]
    let orientation: ShareCardOrientation

    private var points: String { payload.metrics?.first(where: { $0.label.contains("积分") })?.value.text ?? "--" }
    private var winRate: String { payload.insights?.overallWinRate ?? "--" }
    private var mvp: String { payload.insights?.mvpCount.map(String.init) ?? payload.metrics?.first(where: { $0.label.uppercased().contains("MVP") })?.value.text ?? "0" }

    var body: some View {
        ZStack {
            Color(red: 0.035, green: 0.035, blue: 0.04)
            Canvas { context, size in
                var path = Path()
                stride(from: -size.height, through: size.width, by: 34).forEach { x in path.move(to: CGPoint(x: x, y: 0)); path.addLine(to: CGPoint(x: x + size.height, y: size.height)) }
                context.stroke(path, with: .color(Brand.gold.opacity(0.14)), lineWidth: 1)
                context.stroke(Path(CGRect(x: 10, y: 10, width: size.width - 20, height: size.height - 20)), with: .color(Brand.gold), lineWidth: 1)
            }
            if orientation == .portrait { portraitContent } else { landscapeContent }
        }.clipped().environment(\.colorScheme, .dark)
    }

    private var avatarView: some View {
        Group { if let avatar { Image(uiImage: avatar).resizable().scaledToFill() } else { Text(String(payload.player.name.prefix(1))).font(.largeTitle.bold()).foregroundStyle(Brand.gold).frame(maxWidth: .infinity, maxHeight: .infinity).background(Color(red: 0.13, green: 0.11, blue: 0.06)) } }
            .clipShape(Circle()).overlay(Circle().stroke(Brand.gold, lineWidth: 2))
    }

    private var qrView: some View {
        Group { if let qrImage { Image(uiImage: qrImage).interpolation(.none).resizable().scaledToFit() } else { Image(systemName: "qrcode").resizable().scaledToFit().foregroundStyle(.gray).padding(12) } }
            .padding(6).background(.white)
    }

    private var portraitContent: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack(spacing: 15) { avatarView.frame(width: 74, height: 74); VStack(alignment: .leading, spacing: 5) { Text(payload.player.name).font(.system(size: 27, weight: .bold)); Text(payload.player.teamName ?? "未绑定战队").font(.subheadline.bold()).foregroundStyle(Brand.gold); if payload.player.isStarPlayer == true { Label("明星选手", systemImage: "star.fill").font(.caption2.bold()).foregroundStyle(Brand.gold) } }; Spacer() }
            HStack(alignment: .lastTextBaseline) { VStack(alignment: .leading) { Text("赛季排名").font(.caption).foregroundStyle(Brand.gold); Text("#\(payload.player.rank.map(String.init) ?? "--")").font(.system(size: 61, weight: .heavy)).foregroundStyle(Brand.gold) }; Spacer() }
            HStack(spacing: 8) { stat("总积分", points); stat("胜率", winRate); stat("MVP", mvp) }
            achievementText
            Spacer(minLength: 0)
            HStack(alignment: .bottom) { VStack(alignment: .leading, spacing: 4) { Text(scope.competition).font(.caption.bold()).lineLimit(2); Text(scope.season).font(.caption2).foregroundStyle(.white.opacity(0.58)) }; Spacer(); qrView.frame(width: 86, height: 86) }
        }.padding(28).foregroundStyle(Color(red: 0.97, green: 0.94, blue: 0.84))
    }

    private var landscapeContent: some View {
        HStack(spacing: 22) {
            VStack(alignment: .leading, spacing: 14) { HStack { avatarView.frame(width: 76, height: 76); VStack(alignment: .leading) { Text(payload.player.name).font(.system(size: 28, weight: .bold)); Text(payload.player.teamName ?? "未绑定战队").font(.subheadline.bold()).foregroundStyle(Brand.gold) } }; Text("赛季排名").font(.caption).foregroundStyle(Brand.gold); Text("#\(payload.player.rank.map(String.init) ?? "--")").font(.system(size: 62, weight: .heavy)).foregroundStyle(Brand.gold); achievementText; Spacer(); Text(scope.competition).font(.caption.bold()); Text(scope.season).font(.caption2).foregroundStyle(.white.opacity(0.58)) }.frame(maxWidth: .infinity, alignment: .leading)
            VStack(spacing: 12) { HStack(spacing: 8) { stat("总积分", points); stat("胜率", winRate); stat("MVP", mvp) }; Spacer(); qrView.frame(width: 92, height: 92) }
        }.padding(28).foregroundStyle(Color(red: 0.97, green: 0.94, blue: 0.84))
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(spacing: 8) { Text(label).font(.caption2.bold()).foregroundStyle(Brand.gold); Text(value).font(.title3.bold()).minimumScaleFactor(0.7) }
            .frame(maxWidth: .infinity, minHeight: 68).overlay(RoundedRectangle(cornerRadius: 2).stroke(Brand.gold, lineWidth: 1))
    }

    @ViewBuilder private var achievementText: some View {
        if !achievements.isEmpty { VStack(alignment: .leading, spacing: 3) { Text("成就").font(.caption2.bold()).foregroundStyle(Brand.gold); ForEach(achievements) { Text("\($0.title)\(($0.meta).map { " · \($0)" } ?? "")").font(.caption2).lineLimit(1) } } }
    }
}

private struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 0; var x: CGFloat = 0; var y: CGFloat = 0; var line: CGFloat = 0
        for view in subviews { let size = view.sizeThatFits(.unspecified); if x + size.width > width, x > 0 { x = 0; y += line + spacing; line = 0 }; x += size.width + spacing; line = max(line, size.height) }
        return CGSize(width: width, height: y + line)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX; var y = bounds.minY; var line: CGFloat = 0
        for view in subviews { let size = view.sizeThatFits(.unspecified); if x + size.width > bounds.maxX, x > bounds.minX { x = bounds.minX; y += line + spacing; line = 0 }; view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size)); x += size.width + spacing; line = max(line, size.height) }
    }
}
