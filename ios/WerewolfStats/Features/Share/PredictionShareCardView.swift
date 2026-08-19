import Photos
import SwiftUI
import UIKit

private struct PredictionActivityItems: Identifiable {
    let id = UUID()
    let items: [Any]
}

private struct PredictionActivitySheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

private enum PredictionShareError: LocalizedError {
    case wrongDay
    case incompleteRoster
    case invalidRoster
    case incompleteMarkets
    case invalidImage

    var errorDescription: String? {
        switch self {
        case .wrongDay: "服务器未返回所选比赛日的预测，请返回后重新选择日期。"
        case .incompleteRoster: "当天预测名单必须完整为 12 人后才能生成分享图。"
        case .invalidRoster: "当天预测名单存在重复或无效选手，暂时无法生成分享图。"
        case .incompleteMarkets: "当天预测缺少完整的六项分数概率，暂时无法生成分享图。"
        case .invalidImage: "预测分享图渲染失败，请重新生成。"
        }
    }
}

struct PredictionShareCardView: View {
    @Environment(AppState.self) private var app
    let playedOn: String

    @State private var state: LoadState<PredictionsResponse> = .idle
    @State private var qrImage: UIImage?
    @State private var renderedImage: UIImage?
    @State private var activityItems: PredictionActivityItems?
    @State private var alertMessage: String?

    var body: some View {
        Group {
            if app.selectedScope == nil {
                ScopeRequiredView()
            } else {
                switch state {
                case .idle, .loading:
                    LoadingContent(label: "正在生成预测图")
                case .failed(let message):
                    ErrorContent(message: message) { Task { await load(force: true) } }
                case .loaded:
                    editor
                }
            }
        }
        .navigationTitle("当天预测分享图")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $activityItems) { PredictionActivitySheet(items: $0.items) }
        .alert(
            "预测分享图",
            isPresented: Binding(
                get: { alertMessage != nil },
                set: { if !$0 { alertMessage = nil } }
            )
        ) {
            Button("知道了", role: .cancel) {}
        } message: {
            Text(alertMessage ?? "")
        }
        .task(id: app.selectedScope) { await load() }
    }

    private var editor: some View {
        ScrollView {
            VStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Prediction Share").font(.caption.bold()).foregroundStyle(Brand.gold)
                    Text("当天预测分享图").font(.title2.bold())
                    Text("汇总 12 名选手的预测总分和六项分数概率，扫码可进入当天小程序预测。")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if let renderedImage {
                    Image(uiImage: renderedImage)
                        .resizable()
                        .scaledToFit()
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .shadow(radius: 8, y: 4)
                        .accessibilityLabel("\(playedOn) 当天预测分享图预览")
                        .accessibilityIdentifier("prediction-share-preview")
                } else {
                    ProgressView("正在渲染预测图")
                        .frame(maxWidth: .infinity, minHeight: 420)
                }

                HStack {
                    Button("系统分享", systemImage: "square.and.arrow.up") { share() }
                        .buttonStyle(.borderedProminent)
                        .disabled(renderedImage == nil)
                    Button("保存相册", systemImage: "square.and.arrow.down") { save() }
                        .buttonStyle(.bordered)
                        .disabled(renderedImage == nil)
                }
                Button("重新生成", systemImage: "arrow.clockwise") {
                    Task { await load(force: true) }
                }
                .font(.caption)
                Text("微信扫码后进入对应比赛日的小程序预测页。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
        .pageBackground()
    }

    private func load(force: Bool = false) async {
        guard let scope = app.selectedScope else { return }
        state = .loading
        renderedImage = nil
        do {
            let result = try await app.api.get(
                "/api/predictions",
                queryItems: scope.queryItems + [
                    URLQueryItem(name: "played_on", value: playedOn),
                    URLQueryItem(name: "limit", value: "30"),
                    URLQueryItem(name: "offset", value: "0")
                ],
                as: PredictionsResponse.self,
                forceRefresh: force
            )
            try validate(result.value)
            let qrData = try await app.api.imageData(
                "/api/miniprogram/share-code",
                queryItems: [
                    URLQueryItem(name: "share_type", value: "prediction_day"),
                    URLQueryItem(name: "competition", value: scope.competition),
                    URLQueryItem(name: "season", value: scope.season),
                    URLQueryItem(name: "played_on", value: playedOn)
                ]
            )
            guard let qrImage = UIImage(data: qrData) else { throw PredictionShareError.invalidImage }
            self.qrImage = qrImage
            state = .loaded(result.value, isStale: result.isStale)
            render(payload: result.value, scope: scope, qrImage: qrImage)
        } catch is CancellationError {
            return
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    private func validate(_ payload: PredictionsResponse) throws {
        guard payload.selectedDay?.playedOn == playedOn else { throw PredictionShareError.wrongDay }
        guard payload.predictions.count == 12 else { throw PredictionShareError.incompleteRoster }
        let ids = payload.predictions.map(\.playerID)
        guard ids.allSatisfy({ !$0.isEmpty }), Set(ids).count == 12 else {
            throw PredictionShareError.invalidRoster
        }
        guard payload.isPredictionShareReady else { throw PredictionShareError.incompleteMarkets }
    }

    @MainActor private func render(payload: PredictionsResponse, scope: CompetitionScope, qrImage: UIImage) {
        let size = CGSize(width: 375, height: 1_410)
        let card = PredictionDayCard(
            payload: payload,
            scope: scope,
            playedOn: playedOn,
            qrImage: qrImage
        )
        let renderer = ImageRenderer(content: card.frame(width: size.width, height: size.height))
        renderer.scale = 2
        renderer.isOpaque = true
        renderedImage = renderer.uiImage
        if renderedImage == nil { alertMessage = PredictionShareError.invalidImage.localizedDescription }
    }

    private func share() {
        guard let renderedImage else { return }
        activityItems = PredictionActivityItems(items: [renderedImage])
    }

    private func save() {
        guard let renderedImage else { return }
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            Task { @MainActor in
                guard status == .authorized || status == .limited else {
                    alertMessage = "请在系统设置中允许添加照片后重试。"
                    return
                }
                UIImageWriteToSavedPhotosAlbum(renderedImage, nil, nil, nil)
                alertMessage = "预测分享图已保存到照片图库。"
            }
        }
    }
}

private struct PredictionDayCard: View {
    let payload: PredictionsResponse
    let scope: CompetitionScope
    let playedOn: String
    let qrImage: UIImage

    private var predictions: [Prediction] {
        payload.predictions.sorted { ($0.rank ?? Int.max) < ($1.rank ?? Int.max) }
    }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.03, green: 0.035, blue: 0.05), Color(red: 0.065, green: 0.075, blue: 0.1), .black],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Canvas { context, size in
                var path = Path()
                stride(from: -size.height, through: size.width, by: 37).forEach { x in
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x + size.height, y: size.height))
                }
                context.stroke(path, with: .color(Brand.gold.opacity(0.08)), lineWidth: 0.5)
                context.stroke(
                    Path(roundedRect: CGRect(x: 9, y: 9, width: size.width - 18, height: size.height - 18), cornerRadius: 9),
                    with: .color(Brand.gold),
                    lineWidth: 1
                )
            }
            VStack(alignment: .leading, spacing: 7) {
                header
                ForEach(predictions) { prediction in
                    PredictionShareRow(prediction: prediction)
                }
                footer
            }
            .padding(20)
        }
        .clipped()
        .environment(\.colorScheme, .dark)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("GRASS · SCORE FORECAST")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(Brand.gold)
            Text("当天预测总分与分数概率")
                .font(.system(size: 21, weight: .heavy))
            Text(scope.competition)
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(Brand.gold)
                .lineLimit(1)
            Text("\(scope.season) · \(playedOn)")
                .font(.system(size: 10))
                .foregroundStyle(.white.opacity(0.66))
            Text("12 名选手 · \(payload.modelMetadata?.simulations ?? 10_000) 次可复现模拟 · 按预计总分排序")
                .font(.system(size: 9))
                .foregroundStyle(Brand.gold.opacity(0.78))
        }
        .foregroundStyle(Color(red: 0.97, green: 0.94, blue: 0.84))
        .frame(height: 102, alignment: .topLeading)
    }

    private var footer: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 5) {
                Text("预测说明").font(.system(size: 12, weight: .bold)).foregroundStyle(Brand.gold)
                Text("基于历史数据进行可复现模拟")
                Text("结果仅供赛前数据参考")
                Spacer(minLength: 4)
                Text("模型 \(payload.modelMetadata?.version ?? "prediction_model")")
                    .foregroundStyle(.white.opacity(0.58))
                Text("扫码查看当天完整预测")
                    .foregroundStyle(.white.opacity(0.58))
            }
            .font(.system(size: 9))
            Spacer()
            VStack(spacing: 4) {
                Image(uiImage: qrImage)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
                    .padding(5)
                    .background(.white)
                    .frame(width: 92, height: 92)
                Text("扫码查看当天预测").font(.system(size: 8, weight: .bold)).foregroundStyle(Brand.gold)
            }
        }
        .foregroundStyle(Color(red: 0.97, green: 0.94, blue: 0.84))
        .frame(maxHeight: .infinity, alignment: .bottom)
        .padding(.top, 4)
        .overlay(alignment: .top) { Rectangle().fill(Brand.gold.opacity(0.5)).frame(height: 0.5) }
    }
}

private struct PredictionShareRow: View {
    let prediction: Prediction

    private var markets: [PredictionMarket] {
        PredictionsResponse.requiredShareMarketKeys.compactMap { key in
            prediction.marketProbabilities?.first { $0.key == key }
        }
    }

    var body: some View {
        VStack(spacing: 6) {
            HStack(spacing: 8) {
                Text("\(prediction.rank ?? 0)")
                    .font(.system(size: 10, weight: .heavy))
                    .foregroundStyle((prediction.rank ?? 99) <= 3 ? Color.black : Color.white)
                    .frame(width: 22, height: 22)
                    .background((prediction.rank ?? 99) <= 3 ? Brand.gold : Color.white.opacity(0.15), in: Circle())
                VStack(alignment: .leading, spacing: 1) {
                    Text(prediction.playerName).font(.system(size: 13, weight: .heavy)).lineLimit(1)
                    Text(prediction.teamName ?? "未绑定战队")
                        .font(.system(size: 8))
                        .foregroundStyle(.white.opacity(0.62))
                        .lineLimit(1)
                }
                Spacer()
                Text("预测总分").font(.system(size: 8, weight: .bold)).foregroundStyle(Brand.gold.opacity(0.78))
                Text(prediction.scoreText).font(.system(size: 17, weight: .heavy)).foregroundStyle(Brand.gold)
            }
            HStack(spacing: 0) {
                ForEach(markets) { market in
                    VStack(spacing: 2) {
                        Text(market.label).font(.system(size: 7, weight: .bold)).foregroundStyle(Brand.gold.opacity(0.76))
                        Text(market.display ?? market.probability.map { String(format: "%.1f%%", $0 * 100) } ?? "--")
                            .font(.system(size: 9, weight: .heavy))
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .foregroundStyle(Color(red: 0.97, green: 0.94, blue: 0.84))
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(height: 82)
        .background(Color.white.opacity((prediction.rank ?? 0).isMultiple(of: 2) ? 0.075 : 0.045), in: RoundedRectangle(cornerRadius: 7))
        .overlay {
            RoundedRectangle(cornerRadius: 7)
                .stroke((prediction.rank ?? 99) <= 3 ? Brand.gold.opacity(0.58) : Color.white.opacity(0.12), lineWidth: 0.5)
        }
    }
}
