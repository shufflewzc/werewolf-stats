import SwiftUI

struct BrandHero: View {
    let eyebrow: String
    let title: String
    let copy: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(eyebrow).font(.caption.weight(.semibold)).foregroundStyle(.white.opacity(0.72))
            Text(title).font(.largeTitle.bold()).foregroundStyle(.white)
            Text(copy).font(.subheadline).foregroundStyle(.white.opacity(0.8))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(22)
        .background(
            LinearGradient(colors: [Brand.navy, Brand.blue, Brand.gold.opacity(0.9)], startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: 22, style: .continuous)
        )
        .accessibilityElement(children: .combine)
    }
}

struct MetricGrid: View {
    let metrics: [Metric]

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            ForEach(metrics) { metric in
                VStack(alignment: .leading, spacing: 6) {
                    Text(metric.label).font(.caption).foregroundStyle(.secondary)
                    Text(metric.value.text).font(.title2.bold()).contentTransition(.numericText())
                    if let copy = metric.copy, !copy.isEmpty {
                        Text(copy).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 88, alignment: .topLeading)
                .padding(14)
                .background(Brand.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
        }
    }
}

struct SectionHeading: View {
    let title: String
    var note: String? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.title3.bold())
            Spacer()
            if let note { Text(note).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

struct StaleBanner: View {
    var body: some View {
        Label("网络不可用，当前显示上次成功数据，内容可能已过期。", systemImage: "clock.arrow.trianglehead.counterclockwise.rotate.90")
            .font(.caption)
            .foregroundStyle(.orange)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct LoadingContent: View {
    var label = "正在读取赛事数据"
    var body: some View {
        VStack(spacing: 12) { ProgressView(); Text(label).font(.subheadline).foregroundStyle(.secondary) }
            .frame(maxWidth: .infinity, minHeight: 220)
    }
}

struct ErrorContent: View {
    let message: String
    let retry: () -> Void
    var body: some View {
        ContentUnavailableView {
            Label("加载失败", systemImage: "wifi.exclamationmark")
        } description: { Text(message) } actions: { Button("重试", action: retry).buttonStyle(.borderedProminent) }
    }
}

struct ScopeRequiredView: View {
    @Environment(AppState.self) private var app
    var body: some View {
        ContentUnavailableView {
            Label("请先选择赛事", systemImage: "trophy")
        } description: {
            Text("选择赛事和赛季后，才能查看对应的榜单与详情。")
        } actions: {
            Button("前往赛事") { app.selectedTab = .competitions }.buttonStyle(.borderedProminent)
        }
    }
}

struct RemoteImage: View {
    let url: URL?
    var size: CGFloat = 52
    var circular = true

    var body: some View {
        AsyncImage(url: url, transaction: Transaction(animation: .easeInOut)) { phase in
            switch phase {
            case .success(let image): image.resizable().scaledToFill()
            default: Image(systemName: circular ? "person.fill" : "shield.fill").resizable().scaledToFit().padding(size * 0.24).foregroundStyle(.secondary)
            }
        }
        .frame(width: size, height: size)
        .background(Color.secondary.opacity(0.12))
        .clipShape(circular ? AnyShape(Circle()) : AnyShape(RoundedRectangle(cornerRadius: size * 0.2)))
    }
}

struct RankBadge: View {
    let rank: Int?
    var body: some View {
        Text(rank.map(String.init) ?? "–")
            .font(.caption.bold())
            .lineLimit(1)
            .minimumScaleFactor(0.5)
            .allowsTightening(true)
            .foregroundStyle(.white)
            .frame(width: 30, height: 30)
            .background(Brand.navy, in: Circle())
            .accessibilityLabel(rank.map { "排名第 \($0)" } ?? "暂无排名")
    }
}

struct PowerBadge: View {
    let rating: PowerRating?
    var body: some View {
        if let grade = rating?.grade, !grade.isEmpty {
            Text("战力 \(grade)").font(.caption2.bold()).padding(.horizontal, 8).padding(.vertical, 4)
                .foregroundStyle(Brand.navy).background(Brand.paleGold, in: Capsule())
        }
    }
}

extension View {
    func pageBackground() -> some View { background(Brand.page.ignoresSafeArea()) }
}

#Preview("品牌组件") {
    ScrollView {
        VStack(spacing: 16) {
            BrandHero(eyebrow: "实时赛事数据", title: "京城大师赛", copy: "广州赛区 · 2026 S2")
            MetricGrid(metrics: [
                Metric(label: "参赛战队", value: .number(35), copy: "当前赛季"),
                Metric(label: "比赛场次", value: .number(144), copy: "已录入")
            ])
            StaleBanner()
        }.padding()
    }.pageBackground()
}

#Preview("加载状态") { LoadingContent() }
#Preview("错误状态") { ErrorContent(message: "网络连接失败，请检查网络后重试。", retry: {}) }
