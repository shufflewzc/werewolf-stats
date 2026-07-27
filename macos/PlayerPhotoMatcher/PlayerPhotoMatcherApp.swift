import AppKit
import SwiftUI

private let gold = Color(red: 0.83, green: 0.68, blue: 0.22)
private let softGold = Color(red: 0.94, green: 0.83, blue: 0.52)
private let panel = Color(red: 0.09, green: 0.09, blue: 0.09)
private let borderColor = Color.white.opacity(0.12)

struct MatcherSummary: Sendable {
    let rosterCount: Int
    let scannedCount: Int
    let includedCount: Int
    let reviewCount: Int
    let invalidCount: Int
    let unmatchedCount: Int
}

struct MatcherOutcome: Sendable {
    let exitCode: Int32
    let standardOutput: String
    let standardError: String
    let summary: MatcherSummary?
}

struct ReportPayload: Decodable {
    let rows: [ReportRow]
}

struct ReportRow: Decodable {
    let status: String
    let sourceFile: String
    let playerID: String
    let displayName: String
    let teamName: String

    enum CodingKeys: String, CodingKey {
        case status
        case sourceFile = "source_file"
        case playerID = "matched_player_id"
        case displayName = "display_name"
        case teamName = "team_name"
    }
}

struct ConflictCandidate: Identifiable, Hashable {
    let sourceFile: String
    let imageURL: URL

    var id: String { sourceFile }
}

struct ConflictGroup: Identifiable {
    let playerID: String
    let displayName: String
    let teamName: String
    let candidates: [ConflictCandidate]

    var id: String { playerID }
}

enum MatcherLaunchError: LocalizedError {
    case missingEngine
    case couldNotStart(String)

    var errorDescription: String? {
        switch self {
        case .missingEngine:
            return "应用内缺少头像匹配组件，请重新构建或重新复制应用。"
        case .couldNotStart(let message):
            return "无法启动匹配程序：\(message)"
        }
    }
}

@MainActor
final class MatcherViewModel: ObservableObject {
    @Published var folderURL: URL?
    @Published var competition = "京城大师赛广州公开赛"
    @Published var season = "S2"
    @Published var isRunning = false
    @Published var statusText = "请选择包含头像和其他图片的文件夹。"
    @Published var errorText = ""
    @Published var summary: MatcherSummary?
    @Published var outputText = ""
    @Published var previewURL: URL?
    @Published var zipURL: URL?
    @Published var reportURL: URL?
    @Published var conflictGroups: [ConflictGroup] = []
    @Published var manualSelections: [String: String] = [:]

    var canStart: Bool {
        folderURL != nil
            && !competition.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !season.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !isRunning
    }

    var remainingSelectionCount: Int {
        max(conflictGroups.count - manualSelections.count, 0)
    }

    var canConfirmSelections: Bool {
        !conflictGroups.isEmpty && remainingSelectionCount == 0 && !isRunning
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.title = "选择待匹配的图片文件夹"
        panel.prompt = "选择文件夹"
        panel.message = "程序会递归扫描此文件夹，不会修改里面的原图片。"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = false
        if panel.runModal() == .OK, let selectedURL = panel.url {
            folderURL = selectedURL
            resetResult()
            statusText = "已选择文件夹，可以开始匹配。"
        }
    }

    func startMatching() {
        guard let folderURL else { return }
        let competitionValue = competition.trimmingCharacters(in: .whitespacesAndNewlines)
        let seasonValue = season.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !competitionValue.isEmpty, !seasonValue.isEmpty else { return }

        resetResult()
        isRunning = true
        statusText = "正在读取线上名单并扫描图片…"
        runMatching(
            folderURL: folderURL,
            competitionValue: competitionValue,
            seasonValue: seasonValue,
            selectionFileURL: nil
        )
    }

    func selectCandidate(playerID: String, sourceFile: String) {
        manualSelections[playerID] = sourceFile
    }

    func confirmSelections() {
        guard
            let folderURL,
            canConfirmSelections
        else {
            return
        }
        let competitionValue = competition.trimmingCharacters(in: .whitespacesAndNewlines)
        let seasonValue = season.trimmingCharacters(in: .whitespacesAndNewlines)
        let selectionFileURL = folderURL.appendingPathComponent(
            ".matched-player-photo-selections.json"
        )
        do {
            let data = try JSONSerialization.data(
                withJSONObject: manualSelections,
                options: [.prettyPrinted, .sortedKeys]
            )
            try data.write(to: selectionFileURL, options: .atomic)
        } catch {
            errorText = "无法保存头像选择：\(error.localizedDescription)"
            statusText = "人工确认未能保存。"
            return
        }

        isRunning = true
        errorText = ""
        statusText = "正在应用人工选择并生成最终 ZIP…"
        runMatching(
            folderURL: folderURL,
            competitionValue: competitionValue,
            seasonValue: seasonValue,
            selectionFileURL: selectionFileURL
        )
    }

    private func runMatching(
        folderURL: URL,
        competitionValue: String,
        seasonValue: String,
        selectionFileURL: URL?
    ) {
        Task {
            do {
                let outcome = try await Task.detached(priority: .userInitiated) {
                    try runMatcher(
                        folderURL: folderURL,
                        competition: competitionValue,
                        season: seasonValue,
                        selectionFileURL: selectionFileURL
                    )
                }.value

                isRunning = false
                outputText = outcome.standardOutput
                if outcome.exitCode != 0 {
                    errorText = firstUsefulError(
                        standardError: outcome.standardError,
                        standardOutput: outcome.standardOutput
                    )
                    statusText = "匹配未完成，请根据提示处理后重试。"
                    return
                }

                summary = outcome.summary
                previewURL = folderURL.appendingPathComponent("matched-player-photos-preview.html")
                zipURL = folderURL.appendingPathComponent("matched-player-photos.zip")
                reportURL = folderURL.appendingPathComponent("matched-player-photos-report.csv")
                conflictGroups = try loadConflictGroups(from: folderURL)
                if conflictGroups.isEmpty {
                    manualSelections = [:]
                    statusText = "最终 ZIP 已生成，可以上传后台。"
                } else {
                    manualSelections = [:]
                    statusText = "识别完成，请在下方选择每位选手的正确头像。"
                }
            } catch {
                isRunning = false
                errorText = error.localizedDescription
                statusText = "匹配程序未能启动。"
            }
        }
    }

    func openPreview() {
        guard let previewURL else { return }
        NSWorkspace.shared.open(previewURL)
    }

    func revealZip() {
        guard let zipURL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([zipURL])
    }

    func openReport() {
        guard let reportURL else { return }
        NSWorkspace.shared.open(reportURL)
    }

    private func resetResult() {
        errorText = ""
        summary = nil
        outputText = ""
        previewURL = nil
        zipURL = nil
        reportURL = nil
        conflictGroups = []
        manualSelections = [:]
    }
}

private func firstUsefulError(standardError: String, standardOutput: String) -> String {
    let message = standardError.trimmingCharacters(in: .whitespacesAndNewlines)
    if !message.isEmpty {
        return message
    }
    let output = standardOutput.trimmingCharacters(in: .whitespacesAndNewlines)
    return output.isEmpty ? "未知错误，请重试。" : output
}

private func loadConflictGroups(from folderURL: URL) throws -> [ConflictGroup] {
    let reportURL = folderURL.appendingPathComponent(
        "matched-player-photos-report.json"
    )
    let payload = try JSONDecoder().decode(
        ReportPayload.self,
        from: Data(contentsOf: reportURL)
    )
    let duplicateRows = payload.rows.filter {
        $0.status == "duplicate"
            && !$0.playerID.isEmpty
            && !$0.sourceFile.isEmpty
    }
    let groupedRows = Dictionary(grouping: duplicateRows, by: \.playerID)
    return groupedRows.compactMap { playerID, rows in
        guard let first = rows.first else { return nil }
        let candidates = rows
            .map {
                ConflictCandidate(
                    sourceFile: $0.sourceFile,
                    imageURL: folderURL.appendingPathComponent($0.sourceFile)
                )
            }
            .sorted {
                $0.sourceFile.localizedStandardCompare($1.sourceFile) == .orderedAscending
            }
        return ConflictGroup(
            playerID: playerID,
            displayName: first.displayName,
            teamName: first.teamName,
            candidates: candidates
        )
    }
    .sorted {
        if $0.teamName == $1.teamName {
            return $0.displayName.localizedStandardCompare($1.displayName) == .orderedAscending
        }
        return $0.teamName.localizedStandardCompare($1.teamName) == .orderedAscending
    }
}

private func parseCount(prefix: String, from output: String) -> Int {
    for line in output.split(whereSeparator: \.isNewline) {
        let text = String(line).trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.hasPrefix(prefix), let separator = text.firstIndex(of: "：") else {
            continue
        }
        let value = text[text.index(after: separator)...]
        let digits = value.prefix(while: \.isNumber)
        return Int(digits) ?? 0
    }
    return 0
}

private func parseSummary(from output: String) -> MatcherSummary? {
    guard output.contains("已生成 ZIP：") else { return nil }
    return MatcherSummary(
        rosterCount: parseCount(prefix: "名单选手：", from: output),
        scannedCount: parseCount(prefix: "扫描图片：", from: output),
        includedCount: parseCount(prefix: "自动收录：", from: output),
        reviewCount: parseCount(prefix: "需要确认：", from: output),
        invalidCount: parseCount(prefix: "无效图片：", from: output),
        unmatchedCount: parseCount(prefix: "未匹配跳过：", from: output)
    )
}

private func runMatcher(
    folderURL: URL,
    competition: String,
    season: String,
    selectionFileURL: URL?
) throws -> MatcherOutcome {
    guard let engineURL = Bundle.main.url(
        forResource: "player-photo-matcher-cli",
        withExtension: nil
    ) else {
        throw MatcherLaunchError.missingEngine
    }

    let process = Process()
    let outputPipe = Pipe()
    let errorPipe = Pipe()
    process.executableURL = engineURL
    process.arguments = [
        "--folder", folderURL.path,
        "--from-site",
        "--competition", competition,
        "--season", season
    ]
    if let selectionFileURL {
        process.arguments?.append(contentsOf: [
            "--selections", selectionFileURL.path
        ])
    }
    process.standardOutput = outputPipe
    process.standardError = errorPipe

    do {
        try process.run()
    } catch {
        throw MatcherLaunchError.couldNotStart(error.localizedDescription)
    }

    let standardOutputData = outputPipe.fileHandleForReading.readDataToEndOfFile()
    let standardErrorData = errorPipe.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()

    let standardOutput = String(data: standardOutputData, encoding: .utf8) ?? ""
    let standardError = String(data: standardErrorData, encoding: .utf8) ?? ""
    return MatcherOutcome(
        exitCode: process.terminationStatus,
        standardOutput: standardOutput,
        standardError: standardError,
        summary: process.terminationStatus == 0 ? parseSummary(from: standardOutput) : nil
    )
}

struct MetricCard: View {
    let value: Int
    let label: String
    let systemImage: String
    let emphasized: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: systemImage)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(emphasized ? gold : Color.white.opacity(0.72))
            Text("\(value)")
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundStyle(emphasized ? softGold : Color.white)
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Color.white.opacity(0.62))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(15)
        .background(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .fill(emphasized ? gold.opacity(0.09) : Color.white.opacity(0.035))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(
                    emphasized ? gold.opacity(0.38) : borderColor,
                    lineWidth: 1
                )
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label)，\(value)")
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(Color.black)
            .padding(.horizontal, 20)
            .frame(height: 42)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(configuration.isPressed ? softGold : gold)
            )
            .opacity(configuration.isPressed ? 0.86 : 1)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(softGold)
            .padding(.horizontal, 15)
            .frame(height: 38)
            .background(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(configuration.isPressed ? gold.opacity(0.16) : Color.white.opacity(0.045))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .stroke(gold.opacity(0.35), lineWidth: 1)
            )
    }
}

struct CandidateChoiceView: View {
    let candidate: ConflictCandidate
    let playerName: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 9) {
                ZStack(alignment: .topTrailing) {
                    Group {
                        if let image = NSImage(contentsOf: candidate.imageURL) {
                            Image(nsImage: image)
                                .resizable()
                                .scaledToFill()
                        } else {
                            ZStack {
                                Color.white.opacity(0.04)
                                Image(systemName: "photo.badge.exclamationmark")
                                    .font(.system(size: 30))
                                    .foregroundStyle(Color.white.opacity(0.42))
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 180)
                    .clipped()

                    if isSelected {
                        Label("已选择", systemImage: "checkmark.circle.fill")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Color.black)
                            .padding(.horizontal, 9)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(softGold)
                            )
                            .padding(9)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                Text(candidate.sourceFile)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(isSelected ? softGold : Color.white.opacity(0.76))
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(isSelected ? gold.opacity(0.11) : Color.black.opacity(0.2))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .stroke(
                        isSelected ? softGold : borderColor,
                        lineWidth: isSelected ? 2 : 1
                    )
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(playerName)候选头像，\(candidate.sourceFile)")
        .accessibilityValue(isSelected ? "已选择" : "未选择")
        .accessibilityHint("点击选择这张图片作为选手头像")
    }
}

struct ContentView: View {
    @StateObject private var model = MatcherViewModel()

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.035, green: 0.035, blue: 0.035),
                    Color(red: 0.075, green: 0.065, blue: 0.045)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    setupPanel

                    if model.isRunning {
                        progressPanel
                    } else if !model.errorText.isEmpty {
                        errorPanel
                    } else if let summary = model.summary {
                        resultPanel(summary)
                    } else {
                        privacyNote
                    }
                }
                .padding(30)
                .frame(maxWidth: 920)
                .frame(maxWidth: .infinity)
            }
        }
        .frame(minWidth: 760, minHeight: 650)
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 17) {
            ZStack {
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .fill(gold.opacity(0.13))
                    .frame(width: 58, height: 58)
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(gold.opacity(0.46), lineWidth: 1)
                    .frame(width: 58, height: 58)
                Image(systemName: "person.crop.square")
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(softGold)
            }

            VStack(alignment: .leading, spacing: 5) {
                Text("选手头像匹配器")
                    .font(.system(size: 29, weight: .bold, design: .rounded))
                    .foregroundStyle(Color.white)
                Text("从混合图片文件夹中筛选 S2 现有选手，生成后台可直接上传的 ZIP。")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.white.opacity(0.62))
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var setupPanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("匹配设置", systemImage: "slider.horizontal.3")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color.white)

            VStack(alignment: .leading, spacing: 8) {
                Text("图片文件夹")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color.white.opacity(0.72))
                HStack(spacing: 10) {
                    HStack(spacing: 9) {
                        Image(systemName: "folder")
                            .foregroundStyle(gold)
                        Text(model.folderURL?.path ?? "尚未选择")
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .foregroundStyle(
                                model.folderURL == nil
                                    ? Color.white.opacity(0.42)
                                    : Color.white.opacity(0.88)
                            )
                    }
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .fill(Color.black.opacity(0.26))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .stroke(borderColor, lineWidth: 1)
                    )

                    Button(action: model.chooseFolder) {
                        Label("选择…", systemImage: "folder.badge.plus")
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(model.isRunning)
                    .accessibilityLabel("选择图片文件夹")
                }
            }

            HStack(spacing: 14) {
                labeledField(
                    title: "赛事",
                    placeholder: "赛事完整名称",
                    text: $model.competition
                )
                labeledField(
                    title: "赛季",
                    placeholder: "例如 S2",
                    text: $model.season
                )
                .frame(maxWidth: 180)
            }

            Divider().overlay(borderColor)

            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.statusText)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Color.white.opacity(0.82))
                    Text("只读取图片并生成新文件，不会修改原图和服务器数据。")
                        .font(.system(size: 12))
                        .foregroundStyle(Color.white.opacity(0.5))
                }
                Spacer()
                Button(action: model.startMatching) {
                    Label("开始匹配", systemImage: "sparkle.magnifyingglass")
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!model.canStart)
                .opacity(model.canStart ? 1 : 0.45)
                .keyboardShortcut(.return, modifiers: [.command])
                .accessibilityHint("读取线上赛季名单并扫描所选文件夹")
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 17, style: .continuous)
                .fill(panel.opacity(0.94))
        )
        .overlay(
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                .stroke(borderColor, lineWidth: 1)
        )
    }

    private func labeledField(
        title: String,
        placeholder: String,
        text: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Color.white.opacity(0.72))
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .padding(.horizontal, 12)
                .frame(height: 40)
                .background(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .fill(Color.black.opacity(0.26))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .stroke(borderColor, lineWidth: 1)
                )
                .disabled(model.isRunning)
                .accessibilityLabel(title)
        }
        .frame(maxWidth: .infinity)
    }

    private var progressPanel: some View {
        HStack(spacing: 15) {
            ProgressView()
                .controlSize(.small)
                .tint(gold)
            VStack(alignment: .leading, spacing: 4) {
                Text("正在处理")
                    .font(.system(size: 14, weight: .semibold))
                Text("读取线上名单、检查图片格式并生成预览，图片较多时请稍候。")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.white.opacity(0.58))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(gold.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(gold.opacity(0.28), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("正在匹配图片")
    }

    private var errorPanel: some View {
        HStack(alignment: .top, spacing: 13) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Color(red: 0.95, green: 0.53, blue: 0.36))
                .font(.system(size: 18))
            VStack(alignment: .leading, spacing: 7) {
                Text("匹配失败")
                    .font(.system(size: 14, weight: .semibold))
                Text(model.errorText)
                    .font(.system(size: 12))
                    .foregroundStyle(Color.white.opacity(0.7))
                    .textSelection(.enabled)
                Text("检查网络、赛事名和赛季后，可以再次点击“开始匹配”。")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Color.white.opacity(0.88))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.red.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.red.opacity(0.28), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("匹配失败，\(model.errorText)")
    }

    private func resultPanel(_ summary: MatcherSummary) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Label(
                        model.conflictGroups.isEmpty ? "最终 ZIP 已生成" : "请选择正确头像",
                        systemImage: model.conflictGroups.isEmpty
                            ? "checkmark.circle.fill"
                            : "person.crop.square.badge.questionmark"
                    )
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(softGold)
                    Text(
                        model.conflictGroups.isEmpty
                            ? "所有已确认图片都已写入最终 ZIP，可以进入后台上传。"
                            : "每组选一张正确图片；全部选完后再生成最终 ZIP。"
                    )
                        .font(.system(size: 12))
                        .foregroundStyle(Color.white.opacity(0.58))
                }
                Spacer()
                Button(action: model.openPreview) {
                    Label("打开匹配预览", systemImage: "rectangle.and.text.magnifyingglass")
                }
                .buttonStyle(SecondaryButtonStyle())
                .accessibilityHint("在浏览器中查看每张图片的匹配结果")
            }

            if !model.conflictGroups.isEmpty {
                manualConfirmationPanel
            }

            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3),
                spacing: 10
            ) {
                MetricCard(
                    value: summary.rosterCount,
                    label: "名单选手",
                    systemImage: "person.2",
                    emphasized: false
                )
                MetricCard(
                    value: summary.scannedCount,
                    label: "扫描图片",
                    systemImage: "photo.on.rectangle.angled",
                    emphasized: false
                )
                MetricCard(
                    value: summary.includedCount,
                    label: "自动收录",
                    systemImage: "checkmark.seal",
                    emphasized: true
                )
                MetricCard(
                    value: summary.reviewCount,
                    label: "待确认组",
                    systemImage: "questionmark.diamond",
                    emphasized: summary.reviewCount > 0
                )
                MetricCard(
                    value: summary.invalidCount,
                    label: "无效图片",
                    systemImage: "exclamationmark.octagon",
                    emphasized: summary.invalidCount > 0
                )
                MetricCard(
                    value: summary.unmatchedCount,
                    label: "无关／未匹配",
                    systemImage: "minus.magnifyingglass",
                    emphasized: false
                )
            }

            if model.conflictGroups.isEmpty {
                HStack(spacing: 10) {
                    Button(action: model.revealZip) {
                        Label("在 Finder 中显示 ZIP", systemImage: "archivebox")
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    Button(action: model.openReport) {
                        Label("打开 CSV 核对表", systemImage: "tablecells")
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    Spacer()
                    Text("下一步：后台 → 比赛管理 → 批量导入赛季队员头像")
                        .font(.system(size: 11))
                        .foregroundStyle(Color.white.opacity(0.5))
                }
            } else {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(
                            model.remainingSelectionCount == 0
                                ? "已完成全部选择"
                                : "还差 \(model.remainingSelectionCount) 组未选择"
                        )
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(
                            model.remainingSelectionCount == 0
                                ? softGold
                                : Color.white.opacity(0.8)
                        )
                        Text(
                            "已选择 \(model.manualSelections.count) / \(model.conflictGroups.count) 组"
                        )
                        .font(.system(size: 11))
                        .foregroundStyle(Color.white.opacity(0.5))
                    }
                    Spacer()
                    Button(action: model.confirmSelections) {
                        Label("应用选择并生成最终 ZIP", systemImage: "archivebox.fill")
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!model.canConfirmSelections)
                    .opacity(model.canConfirmSelections ? 1 : 0.42)
                    .accessibilityHint(
                        model.canConfirmSelections
                            ? "将选中的头像写入最终压缩包"
                            : "请先为每位待确认选手选择一张头像"
                    )
                }
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 17, style: .continuous)
                .fill(panel.opacity(0.94))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 17, style: .continuous)
                .stroke(gold.opacity(0.3), lineWidth: 1)
        )
    }

    private var manualConfirmationPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label(
                    "\(model.conflictGroups.count) 组选手需要确认",
                    systemImage: "rectangle.2.swap"
                )
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Color.white)
                Spacer()
                Text("点击图片即可选择，可随时改选")
                    .font(.system(size: 11))
                    .foregroundStyle(Color.white.opacity(0.5))
            }

            ForEach(Array(model.conflictGroups.enumerated()), id: \.element.id) { index, group in
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("\(index + 1). \(group.displayName)")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(Color.white)
                        Text(group.teamName.isEmpty ? "未分队" : group.teamName)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(softGold.opacity(0.8))
                        Spacer()
                        if model.manualSelections[group.playerID] != nil {
                            Label("已选择", systemImage: "checkmark.circle.fill")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(softGold)
                        } else {
                            Label("待选择", systemImage: "circle")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(Color.white.opacity(0.46))
                        }
                    }

                    LazyVGrid(
                        columns: Array(
                            repeating: GridItem(.flexible(), spacing: 12),
                            count: min(max(group.candidates.count, 1), 3)
                        ),
                        spacing: 12
                    ) {
                        ForEach(group.candidates) { candidate in
                            CandidateChoiceView(
                                candidate: candidate,
                                playerName: group.displayName,
                                isSelected:
                                    model.manualSelections[group.playerID]
                                        == candidate.sourceFile
                            ) {
                                model.selectCandidate(
                                    playerID: group.playerID,
                                    sourceFile: candidate.sourceFile
                                )
                            }
                        }
                    }
                }
                .padding(15)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color.white.opacity(0.025))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(
                            model.manualSelections[group.playerID] == nil
                                ? borderColor
                                : gold.opacity(0.32),
                            lineWidth: 1
                        )
                )
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .fill(Color.black.opacity(0.18))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(gold.opacity(0.22), lineWidth: 1)
        )
    }

    private var privacyNote: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "lock.shield")
                .foregroundStyle(gold)
            Text("程序只通过公开接口读取当前赛季选手名单。你的本地图片不会上传到网站，只有你最后手动上传 ZIP 时才会写入头像。")
                .font(.system(size: 12))
                .foregroundStyle(Color.white.opacity(0.58))
        }
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
    }
}

@main
struct PlayerPhotoMatcherApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
