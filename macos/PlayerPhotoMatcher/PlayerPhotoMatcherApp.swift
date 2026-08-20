import AppKit
import Security
import SwiftUI

private let siteURL = "https://wolf.metauniverse-cn.xyz"
private let maxUploadArchiveBytes: Int64 = 45 * 1024 * 1024
private let gold = Color(red: 0.83, green: 0.68, blue: 0.22)
private let softGold = Color(red: 0.94, green: 0.83, blue: 0.52)
private let panel = Color(red: 0.09, green: 0.09, blue: 0.09)
private let borderColor = Color.white.opacity(0.12)

struct CompetitionCatalogPayload: Decodable {
    let cards: [CompetitionCatalogCard]
}

struct CompetitionCatalogCard: Decodable, Hashable, Sendable, Identifiable {
    let competitionName: String
    let regionName: String
    let seriesName: String
    let seasons: [String]

    var id: String { "\(regionName)\u{1f}\(competitionName)" }
    var displayName: String { "\(regionName) · \(competitionName)" }

    enum CodingKeys: String, CodingKey {
        case competitionName = "competition_name"
        case regionName = "region_name"
        case seriesName = "series_name"
        case seasons
    }
}

struct MatcherSummary: Sendable {
    let rosterCount: Int
    let scannedCount: Int
    let includedCount: Int
    let reviewCount: Int
    let invalidCount: Int
    let unmatchedCount: Int
    let compressedCount: Int
}

struct MatcherOutcome: Sendable {
    let exitCode: Int32
    let standardOutput: String
    let standardError: String
    let summary: MatcherSummary?
}

struct ReportPayload: Decodable {
    let scopeLabel: String
    let players: [ReportPlayer]
    let rows: [ReportRow]

    enum CodingKeys: String, CodingKey {
        case scopeLabel = "scope_label"
        case players
        case rows
    }
}

struct ReportPlayer: Decodable, Hashable, Sendable, Identifiable {
    let playerID: String
    let displayName: String
    let teamName: String

    var id: String { playerID }
    var searchText: String {
        "\(displayName) \(teamName) \(playerID)".localizedLowercase
    }

    enum CodingKeys: String, CodingKey {
        case playerID = "player_id"
        case displayName = "display_name"
        case teamName = "team_name"
    }
}

struct ReportRow: Decodable, Hashable, Sendable {
    let status: String
    let sourceFile: String
    let playerID: String
    let displayName: String
    let teamName: String
    let matchMethod: String
    let reason: String
    let suggestion: String
    let compressionNote: String?

    enum CodingKeys: String, CodingKey {
        case status
        case sourceFile = "source_file"
        case playerID = "matched_player_id"
        case displayName = "display_name"
        case teamName = "team_name"
        case matchMethod = "match_method"
        case reason
        case suggestion
        case compressionNote = "compression_note"
    }
}

struct UploadTargetsPayload: Decodable, Sendable {
    let targets: [UploadTarget]
    let token: UploadTokenInfo
}

struct UploadTarget: Decodable, Hashable, Sendable {
    let competitionName: String
    let seasonName: String

    enum CodingKeys: String, CodingKey {
        case competitionName = "competition_name"
        case seasonName = "season_name"
    }
}

struct UploadTokenInfo: Decodable, Sendable {
    let name: String?
    let expiresAt: String?

    enum CodingKeys: String, CodingKey {
        case name
        case expiresAt = "expires_at"
    }
}

struct PlayerPhotoUploadPayload: Decodable, Sendable {
    let status: String
    let batchID: String?
    let message: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case status
        case batchID = "batch_id"
        case message
        case error
    }
}

struct UploadJobPayload: Decodable, Sendable {
    let status: String
    let summary: String
}

enum PhotoFilter: String, CaseIterable, Identifiable {
    case attention = "需处理"
    case all = "全部图片"
    case included = "已收录"

    var id: String { rawValue }
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

enum CatalogLoadError: LocalizedError {
    case invalidURL
    case invalidResponse
    case emptyCatalog

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "赛事目录地址无效。"
        case .invalidResponse:
            return "正式站返回的赛事目录格式不正确。"
        case .emptyCatalog:
            return "正式站暂时没有可选择的赛事赛季。"
        }
    }
}

enum UploadServiceError: LocalizedError {
    case invalidURL
    case invalidResponse
    case server(String)
    case targetNotAllowed
    case missingBatchID
    case timedOut

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "上传地址无效。"
        case .invalidResponse:
            return "服务器返回了无法识别的上传结果。"
        case .server(let message):
            return message
        case .targetNotAllowed:
            return "当前令牌没有所选赛事赛季的头像上传权限。"
        case .missingBatchID:
            return "服务器没有返回头像导入任务编号。"
        case .timedOut:
            return "头像已提交，但等待后台处理超时。可稍后在后台导入记录中查看结果。"
        }
    }
}

enum UploadTokenStore {
    private static let service = "cn.metauniverse.werewolf.player-photo-matcher"
    private static let account = "data-upload-token"

    static func load() -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let token = String(data: data, encoding: .utf8) else {
            return ""
        }
        return token
    }

    static func save(_ token: String) throws {
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let data = Data(token.utf8)
        let status = SecItemUpdate(
            baseQuery as CFDictionary,
            [kSecValueData as String: data] as CFDictionary
        )
        if status == errSecItemNotFound {
            var insert = baseQuery
            insert[kSecValueData as String] = data
            let addStatus = SecItemAdd(insert as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw UploadServiceError.server("无法安全保存上传令牌（\(addStatus)）。")
            }
        } else if status != errSecSuccess {
            throw UploadServiceError.server("无法安全保存上传令牌（\(status)）。")
        }
    }

    static func remove() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }
}

@MainActor
final class MatcherViewModel: ObservableObject {
    @Published var folderURL: URL?
    @Published var catalogCards: [CompetitionCatalogCard] = []
    @Published var selectedCompetitionID = ""
    @Published var selectedSeason = ""
    @Published var isCatalogLoading = false
    @Published var catalogError = ""
    @Published var isRunning = false
    @Published var statusText = "请选择赛事赛季和包含头像的文件夹。"
    @Published var errorText = ""
    @Published var summary: MatcherSummary?
    @Published var outputText = ""
    @Published var previewURL: URL?
    @Published var zipURL: URL?
    @Published var reportURL: URL?
    @Published var reportScopeLabel = ""
    @Published var rosterPlayers: [ReportPlayer] = []
    @Published var photoRows: [ReportRow] = []
    @Published var manualAssignments: [String: String] = [:]
    @Published var rejectedSources: Set<String> = []
    @Published var photoFilter: PhotoFilter = .attention
    @Published var activeSourceFile = ""
    @Published var isPlayerChooserPresented = false
    @Published var isAssignmentConflictPresented = false
    @Published var assignmentConflictMessage = ""
    @Published var uploadTokenDraft = ""
    @Published var uploadTokenStatus = ""
    @Published var uploadTokenError = ""
    @Published var isVerifyingUploadToken = false
    @Published var isUploading = false
    @Published var uploadStatus = ""
    @Published var uploadError = ""
    @Published var uploadedBatchID = ""
    @Published var isResultDirty = false
    @Published var didUploadCurrentResult = false
    private var pendingAssignment: (playerID: String, sourceFile: String)?
    private var currentUploadRequestID = ""

    init() {
        uploadTokenDraft = UploadTokenStore.load()
        if !uploadTokenDraft.isEmpty {
            uploadTokenStatus = "已从钥匙串读取上传令牌"
        }
    }

    var selectedCompetition: CompetitionCatalogCard? {
        catalogCards.first { $0.id == selectedCompetitionID }
    }

    var availableSeasons: [String] {
        selectedCompetition?.seasons ?? []
    }

    var canStart: Bool {
        folderURL != nil
            && selectedCompetition != nil
            && !selectedSeason.isEmpty
            && !isRunning
            && !isCatalogLoading
    }

    var canRegenerate: Bool {
        summary != nil && !isRunning
    }

    var hasUploadToken: Bool {
        uploadTokenDraft.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("wdu_")
    }

    var canUpload: Bool {
        zipURL != nil
            && (summary?.includedCount ?? 0) > 0
            && selectedCompetition != nil
            && !selectedSeason.isEmpty
            && hasUploadToken
            && !isRunning
            && !isUploading
            && !isResultDirty
            && !didUploadCurrentResult
    }

    var manualChangeCount: Int {
        manualAssignments.count + rejectedSources.count
    }

    var filteredPhotoRows: [ReportRow] {
        switch photoFilter {
        case .all:
            return photoRows
        case .included:
            return photoRows.filter { row in
                if rejectedSources.contains(row.sourceFile) { return false }
                return manualPlayerID(for: row.sourceFile) != nil || row.status == "included"
            }
        case .attention:
            return photoRows.filter { row in
                if rejectedSources.contains(row.sourceFile)
                    || manualPlayerID(for: row.sourceFile) != nil {
                    return false
                }
                return ["duplicate", "ambiguous", "unmatched", "invalid"].contains(row.status)
            }
        }
    }

    var unresolvedPhotoCount: Int {
        photoRows.filter { row in
            !rejectedSources.contains(row.sourceFile)
                && manualPlayerID(for: row.sourceFile) == nil
                && ["duplicate", "ambiguous", "unmatched", "invalid"].contains(row.status)
        }.count
    }

    func loadCatalogIfNeeded() {
        if catalogCards.isEmpty && !isCatalogLoading { loadCatalog() }
    }

    func loadCatalog() {
        isCatalogLoading = true
        catalogError = ""
        Task {
            do {
                let cards = try await fetchCompetitionCatalog().filter { !$0.seasons.isEmpty }
                guard !cards.isEmpty else { throw CatalogLoadError.emptyCatalog }
                catalogCards = cards
                isCatalogLoading = false
            } catch {
                catalogCards = []
                selectedCompetitionID = ""
                selectedSeason = ""
                catalogError = error.localizedDescription
                isCatalogLoading = false
            }
        }
    }

    func competitionDidChange() {
        selectedSeason = ""
        resetResult(clearManualChanges: true)
        statusText = selectedCompetition == nil ? "请选择赛事。" : "请选择该赛事的赛季。"
    }

    func seasonDidChange() {
        resetResult(clearManualChanges: true)
        if !selectedSeason.isEmpty {
            statusText = folderURL == nil
                ? "已选择赛事赛季，请继续选择图片文件夹。"
                : "设置完成，可以开始匹配。"
        }
    }

    func chooseFolder() {
        let openPanel = NSOpenPanel()
        openPanel.title = "选择待匹配的图片文件夹"
        openPanel.prompt = "选择文件夹"
        openPanel.message = "程序会递归扫描此文件夹和所有子文件夹，不会修改原图片。"
        openPanel.canChooseDirectories = true
        openPanel.canChooseFiles = false
        openPanel.allowsMultipleSelection = false
        openPanel.canCreateDirectories = false
        if openPanel.runModal() == .OK, let selectedURL = openPanel.url {
            folderURL = selectedURL
            resetResult(clearManualChanges: true)
            statusText = selectedSeason.isEmpty
                ? "已选择文件夹，请继续选择赛事赛季。"
                : "已选择文件夹，将递归扫描全部子目录。"
        }
    }

    func startMatching() {
        guard let folderURL, let competition = selectedCompetition else { return }
        guard !selectedSeason.isEmpty else { return }
        resetResult(clearManualChanges: true)
        isRunning = true
        statusText = "正在读取线上名单并递归扫描图片…"
        runMatching(
            folderURL: folderURL,
            competitionValue: competition.competitionName,
            seasonValue: selectedSeason,
            selectionFileURL: nil
        )
    }

    func presentPlayerChooser(for sourceFile: String) {
        guard !sourceFile.isEmpty else { return }
        activeSourceFile = sourceFile
        isPlayerChooserPresented = true
    }

    func assignPlayer(_ playerID: String, to sourceFile: String) {
        let existingSource = manualAssignments[playerID]
        let existingPlayerID = manualPlayerID(for: sourceFile)
        if (existingSource != nil && existingSource != sourceFile)
            || (existingPlayerID != nil && existingPlayerID != playerID) {
            var details: [String] = []
            if let existingSource, existingSource != sourceFile {
                details.append("该选手已人工选择“\(existingSource)”")
            }
            if let existingPlayerID,
               existingPlayerID != playerID,
               let existingPlayer = rosterPlayers.first(where: { $0.playerID == existingPlayerID }) {
                details.append("这张图片已分配给“\(existingPlayer.displayName)”")
            }
            pendingAssignment = (playerID, sourceFile)
            assignmentConflictMessage = details.joined(separator: "；") + "。确认后将使用本次选择。"
            isPlayerChooserPresented = false
            isAssignmentConflictPresented = true
            return
        }
        commitAssignment(playerID, to: sourceFile)
    }

    func confirmAssignmentReplacement() {
        guard let pendingAssignment else { return }
        commitAssignment(pendingAssignment.playerID, to: pendingAssignment.sourceFile)
        self.pendingAssignment = nil
        isAssignmentConflictPresented = false
    }

    func cancelAssignmentReplacement() {
        pendingAssignment = nil
        isAssignmentConflictPresented = false
    }

    private func commitAssignment(_ playerID: String, to sourceFile: String) {
        var updated = manualAssignments
        for (assignedPlayerID, assignedSource) in updated where assignedSource == sourceFile {
            updated.removeValue(forKey: assignedPlayerID)
        }
        updated[playerID] = sourceFile
        manualAssignments = updated
        rejectedSources.remove(sourceFile)
        isResultDirty = true
        isPlayerChooserPresented = false
    }

    func markNotImported(_ sourceFile: String) {
        manualAssignments = manualAssignments.filter { $0.value != sourceFile }
        rejectedSources.insert(sourceFile)
        isResultDirty = true
    }

    func restoreAutomatic(_ sourceFile: String) {
        manualAssignments = manualAssignments.filter { $0.value != sourceFile }
        rejectedSources.remove(sourceFile)
        isResultDirty = true
    }

    func manualPlayerID(for sourceFile: String) -> String? {
        manualAssignments.first { $0.value == sourceFile }?.key
    }

    func effectivePlayer(for row: ReportRow) -> ReportPlayer? {
        if rejectedSources.contains(row.sourceFile) { return nil }
        let playerID = manualPlayerID(for: row.sourceFile) ?? row.playerID
        return rosterPlayers.first { $0.playerID == playerID }
    }

    func applyManualChanges() {
        guard let folderURL, let competition = selectedCompetition, canRegenerate else { return }
        let selectionFileURL = folderURL.appendingPathComponent(
            ".matched-player-photo-selections.json"
        )
        do {
            let payload: [String: Any] = [
                "version": 2,
                "assignments": manualAssignments,
                "rejected_sources": rejectedSources.sorted(),
            ]
            let data = try JSONSerialization.data(
                withJSONObject: payload,
                options: [.prettyPrinted, .sortedKeys]
            )
            try data.write(to: selectionFileURL, options: .atomic)
        } catch {
            errorText = "无法保存头像选择：\(error.localizedDescription)"
            statusText = "人工选择未能保存。"
            return
        }

        isRunning = true
        errorText = ""
        statusText = manualChangeCount == 0
            ? "正在恢复自动匹配并重新生成 ZIP…"
            : "正在应用人工处理并重新生成 ZIP…"
        runMatching(
            folderURL: folderURL,
            competitionValue: competition.competitionName,
            seasonValue: selectedSeason,
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

                let report = try loadReport(from: folderURL)
                summary = outcome.summary
                reportScopeLabel = report.scopeLabel
                rosterPlayers = report.players
                photoRows = report.rows.filter { !$0.sourceFile.isEmpty }
                previewURL = folderURL.appendingPathComponent("matched-player-photos-preview.html")
                zipURL = folderURL.appendingPathComponent("matched-player-photos.zip")
                reportURL = folderURL.appendingPathComponent("matched-player-photos-report.csv")
                photoFilter = unresolvedPhotoCount > 0 ? .attention : .all
                isResultDirty = false
                uploadStatus = ""
                uploadError = ""
                uploadedBatchID = ""
                didUploadCurrentResult = false
                currentUploadRequestID = ""
                statusText = selectionFileURL == nil
                    ? "匹配完成。可检查全部图片、修正选手或直接使用 ZIP。"
                    : "人工处理已应用，最终 ZIP 已重新生成。"
            } catch {
                isRunning = false
                errorText = error.localizedDescription
                statusText = "匹配程序未能完成。"
            }
        }
    }

    func verifyAndSaveUploadToken() {
        let token = uploadTokenDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard token.hasPrefix("wdu_") else {
            uploadTokenError = "请输入个人中心创建的 wdu_ 上传令牌。"
            uploadTokenStatus = ""
            return
        }
        isVerifyingUploadToken = true
        uploadTokenError = ""
        uploadTokenStatus = "正在验证令牌…"
        Task {
            do {
                let payload = try await fetchUploadTargets(token: token)
                try UploadTokenStore.save(token)
                uploadTokenDraft = token
                let tokenName = payload.token.name?.trimmingCharacters(in: .whitespacesAndNewlines)
                if let tokenName, !tokenName.isEmpty {
                    uploadTokenStatus = "令牌有效 · \(tokenName)"
                } else {
                    uploadTokenStatus = "令牌有效 · 可上传赛季 \(payload.targets.count) 个"
                }
            } catch {
                uploadTokenStatus = ""
                uploadTokenError = error.localizedDescription
            }
            isVerifyingUploadToken = false
        }
    }

    func removeUploadToken() {
        UploadTokenStore.remove()
        uploadTokenDraft = ""
        uploadTokenStatus = "上传令牌已移除"
        uploadTokenError = ""
    }

    func openUploadTokenPage() {
        if let url = URL(string: siteURL + "/profile") {
            NSWorkspace.shared.open(url)
        }
    }

    func uploadMatchedPhotos() {
        guard canUpload,
              let zipURL,
              let competition = selectedCompetition else { return }
        if let fileSize = try? zipURL.resourceValues(forKeys: [.fileSizeKey]).fileSize,
           Int64(fileSize) > maxUploadArchiveBytes {
            uploadError = String(
                format: "当前 ZIP 为 %.1f MB，请重新匹配生成小于 45 MB 的上传包。",
                Double(fileSize) / 1024 / 1024
            )
            uploadStatus = ""
            return
        }
        let token = uploadTokenDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        isUploading = true
        uploadError = ""
        uploadedBatchID = ""
        uploadStatus = "正在上传头像 ZIP…"
        if currentUploadRequestID.isEmpty {
            currentUploadRequestID = "photo-\(UUID().uuidString.lowercased())"
        }
        Task {
            do {
                let allowedTargets = try await fetchUploadTargets(token: token).targets
                guard allowedTargets.contains(where: {
                    $0.competitionName == competition.competitionName
                        && $0.seasonName == selectedSeason
                }) else {
                    throw UploadServiceError.targetNotAllowed
                }
                let response = try await uploadPlayerPhotoArchive(
                    zipURL: zipURL,
                    competition: competition.competitionName,
                    season: selectedSeason,
                    token: token,
                    requestID: currentUploadRequestID
                )
                guard response.status == "queued",
                      let batchID = response.batchID,
                      !batchID.isEmpty else {
                    throw UploadServiceError.server(
                        response.error ?? response.message ?? UploadServiceError.missingBatchID.localizedDescription
                    )
                }
                uploadedBatchID = batchID
                uploadStatus = response.message ?? "头像已进入后台导入队列。"
                let job = try await waitForUploadJob(batchID: batchID, token: token)
                guard job.status == "succeeded" else {
                    throw UploadServiceError.server(
                        job.summary.isEmpty ? "头像导入未完成：\(job.status)" : job.summary
                    )
                }
                uploadStatus = job.summary.isEmpty ? "头像上传并导入完成。" : job.summary
                didUploadCurrentResult = true
                statusText = "头像已上传到 \(competition.competitionName) / \(selectedSeason)。"
            } catch {
                uploadError = error.localizedDescription
                uploadStatus = ""
            }
            isUploading = false
        }
    }

    func openPreview() {
        if let previewURL { NSWorkspace.shared.open(previewURL) }
    }

    func revealZip() {
        if let zipURL { NSWorkspace.shared.activateFileViewerSelecting([zipURL]) }
    }

    func openReport() {
        if let reportURL { NSWorkspace.shared.open(reportURL) }
    }

    private func resetResult(clearManualChanges: Bool) {
        errorText = ""
        summary = nil
        outputText = ""
        previewURL = nil
        zipURL = nil
        reportURL = nil
        reportScopeLabel = ""
        rosterPlayers = []
        photoRows = []
        photoFilter = .attention
        isResultDirty = false
        isUploading = false
        uploadStatus = ""
        uploadError = ""
        uploadedBatchID = ""
        didUploadCurrentResult = false
        currentUploadRequestID = ""
        if clearManualChanges {
            manualAssignments = [:]
            rejectedSources = []
        }
    }
}

private func fetchCompetitionCatalog() async throws -> [CompetitionCatalogCard] {
    guard var components = URLComponents(string: siteURL + "/api/competitions") else {
        throw CatalogLoadError.invalidURL
    }
    components.queryItems = [URLQueryItem(name: "grouped", value: "1")]
    guard let url = components.url else { throw CatalogLoadError.invalidURL }
    var request = URLRequest(url: url)
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    request.setValue("werewolf-stats-player-photo-matcher/1.3.1", forHTTPHeaderField: "User-Agent")
    request.timeoutInterval = 20
    let (data, response) = try await URLSession.shared.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse,
          (200..<300).contains(httpResponse.statusCode) else {
        throw CatalogLoadError.invalidResponse
    }
    do {
        return try JSONDecoder().decode(CompetitionCatalogPayload.self, from: data).cards
    } catch {
        throw CatalogLoadError.invalidResponse
    }
}

private func serverErrorMessage(from data: Data, fallback: String) -> String {
    guard let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        return fallback
    }
    return String(describing: payload["error"] ?? payload["message"] ?? fallback)
}

private func authorizedRequest(url: URL, token: String) -> URLRequest {
    var request = URLRequest(url: url)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    request.setValue("werewolf-stats-player-photo-matcher/1.3", forHTTPHeaderField: "User-Agent")
    request.timeoutInterval = 30
    return request
}

private func fetchUploadTargets(token: String) async throws -> UploadTargetsPayload {
    guard let url = URL(string: siteURL + "/api/data-upload/targets") else {
        throw UploadServiceError.invalidURL
    }
    let (data, response) = try await URLSession.shared.data(
        for: authorizedRequest(url: url, token: token)
    )
    guard let httpResponse = response as? HTTPURLResponse else {
        throw UploadServiceError.invalidResponse
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
        throw UploadServiceError.server(
            serverErrorMessage(from: data, fallback: "上传令牌验证失败。")
        )
    }
    do {
        return try JSONDecoder().decode(UploadTargetsPayload.self, from: data)
    } catch {
        throw UploadServiceError.invalidResponse
    }
}

private func appendMultipartText(_ text: String, to body: inout Data) {
    body.append(Data(text.utf8))
}

private func uploadPlayerPhotoArchive(
    zipURL: URL,
    competition: String,
    season: String,
    token: String,
    requestID: String
) async throws -> PlayerPhotoUploadPayload {
    guard let url = URL(string: siteURL + "/api/data-upload/player-photos") else {
        throw UploadServiceError.invalidURL
    }
    let boundary = "PlayerPhotoMatcher-\(UUID().uuidString)"
    var body = Data()
    let fields = [
        "competition_name": competition,
        "season_name": season,
        "request_id": requestID,
    ]
    for (name, value) in fields {
        appendMultipartText("--\(boundary)\r\n", to: &body)
        appendMultipartText(
            "Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n",
            to: &body
        )
        appendMultipartText("\(value)\r\n", to: &body)
    }
    let zipData = try Data(contentsOf: zipURL, options: [.mappedIfSafe])
    appendMultipartText("--\(boundary)\r\n", to: &body)
    appendMultipartText(
        "Content-Disposition: form-data; name=\"player_photo_zip\"; filename=\"matched-player-photos.zip\"\r\n",
        to: &body
    )
    appendMultipartText("Content-Type: application/zip\r\n\r\n", to: &body)
    body.append(zipData)
    appendMultipartText("\r\n--\(boundary)--\r\n", to: &body)

    var request = authorizedRequest(url: url, token: token)
    request.httpMethod = "POST"
    request.timeoutInterval = 120
    request.setValue(
        "multipart/form-data; boundary=\(boundary)",
        forHTTPHeaderField: "Content-Type"
    )
    let (data, response) = try await URLSession.shared.upload(for: request, from: body)
    guard let httpResponse = response as? HTTPURLResponse else {
        throw UploadServiceError.invalidResponse
    }
    if httpResponse.statusCode == 413 {
        throw UploadServiceError.server("头像 ZIP 超过服务器上传上限，请重新匹配生成较小的上传包。")
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
        throw UploadServiceError.server(
            serverErrorMessage(from: data, fallback: "头像上传失败（HTTP \(httpResponse.statusCode)）。")
        )
    }
    do {
        return try JSONDecoder().decode(PlayerPhotoUploadPayload.self, from: data)
    } catch {
        throw UploadServiceError.invalidResponse
    }
}

private func fetchUploadJob(batchID: String, token: String) async throws -> UploadJobPayload {
    guard let encodedBatchID = batchID.addingPercentEncoding(
        withAllowedCharacters: .urlPathAllowed
    ), let url = URL(string: siteURL + "/api/data-upload/jobs/" + encodedBatchID) else {
        throw UploadServiceError.invalidURL
    }
    let (data, response) = try await URLSession.shared.data(
        for: authorizedRequest(url: url, token: token)
    )
    guard let httpResponse = response as? HTTPURLResponse else {
        throw UploadServiceError.invalidResponse
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
        throw UploadServiceError.server(
            serverErrorMessage(from: data, fallback: "读取头像导入任务失败。")
        )
    }
    do {
        return try JSONDecoder().decode(UploadJobPayload.self, from: data)
    } catch {
        throw UploadServiceError.invalidResponse
    }
}

private func waitForUploadJob(batchID: String, token: String) async throws -> UploadJobPayload {
    for _ in 0..<120 {
        let job = try await fetchUploadJob(batchID: batchID, token: token)
        if !["queued", "running"].contains(job.status) {
            return job
        }
        try await Task.sleep(nanoseconds: 1_000_000_000)
    }
    throw UploadServiceError.timedOut
}

private func firstUsefulError(standardError: String, standardOutput: String) -> String {
    let message = standardError.trimmingCharacters(in: .whitespacesAndNewlines)
    if !message.isEmpty { return message }
    let output = standardOutput.trimmingCharacters(in: .whitespacesAndNewlines)
    return output.isEmpty ? "未知错误，请重试。" : output
}

private func loadReport(from folderURL: URL) throws -> ReportPayload {
    let reportURL = folderURL.appendingPathComponent("matched-player-photos-report.json")
    return try JSONDecoder().decode(ReportPayload.self, from: Data(contentsOf: reportURL))
}

private func parseCount(prefix: String, from output: String) -> Int {
    for line in output.split(whereSeparator: \.isNewline) {
        let text = String(line).trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.hasPrefix(prefix), let separator = text.firstIndex(of: "：") else { continue }
        let value = text[text.index(after: separator)...]
        let digits = value.prefix(while: \.isNumber)
        return Int(digits) ?? 0
    }
    return 0
}

private func parseSummary(from output: String) -> MatcherSummary? {
    guard output.contains("已生成 ZIP：") else { return nil }
    let finalIncluded = parseCount(prefix: "最终收录：", from: output)
    let legacyIncluded = parseCount(prefix: "自动收录：", from: output)
    return MatcherSummary(
        rosterCount: parseCount(prefix: "名单选手：", from: output),
        scannedCount: parseCount(prefix: "扫描图片：", from: output),
        includedCount: output.contains("最终收录：") ? finalIncluded : legacyIncluded,
        reviewCount: parseCount(prefix: "需要确认：", from: output),
        invalidCount: parseCount(prefix: "无效图片：", from: output),
        unmatchedCount: parseCount(prefix: "未匹配跳过：", from: output),
        compressedCount: parseCount(prefix: "自动压缩：", from: output)
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
    ) else { throw MatcherLaunchError.missingEngine }

    let process = Process()
    let outputPipe = Pipe()
    let errorPipe = Pipe()
    process.executableURL = engineURL
    process.arguments = [
        "--folder", folderURL.path,
        "--from-site",
        "--competition", competition,
        "--season", season,
    ]
    if let selectionFileURL {
        process.arguments?.append(contentsOf: ["--selections", selectionFileURL.path])
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

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(Color.black)
            .padding(.horizontal, 20)
            .frame(height: 42)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
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
            .padding(.horizontal, 14)
            .frame(height: 38)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(configuration.isPressed ? gold.opacity(0.16) : Color.white.opacity(0.045))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(gold.opacity(0.35), lineWidth: 1)
            )
    }
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
                .font(.system(size: 27, weight: .bold, design: .rounded))
                .foregroundStyle(emphasized ? softGold : Color.white)
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Color.white.opacity(0.62))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(emphasized ? gold.opacity(0.09) : Color.white.opacity(0.035))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(emphasized ? gold.opacity(0.38) : borderColor, lineWidth: 1)
        )
    }
}

struct PlayerChooserView: View {
    let sourceFile: String
    let players: [ReportPlayer]
    let selectedPlayerID: String?
    let onSelect: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var searchText = ""

    private var filteredPlayers: [ReportPlayer] {
        let keyword = searchText.trimmingCharacters(in: .whitespacesAndNewlines).localizedLowercase
        if keyword.isEmpty { return players }
        return players.filter { $0.searchText.contains(keyword) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("选择选手").font(.system(size: 21, weight: .bold))
                    Text(sourceFile)
                        .font(.system(size: 12))
                        .foregroundStyle(Color.secondary)
                        .lineLimit(2)
                        .truncationMode(.middle)
                }
                Spacer()
                Button(action: { dismiss() }) { Image(systemName: "xmark") }
                    .buttonStyle(.borderless)
                    .help("关闭")
            }
            TextField("搜索姓名、战队或选手 ID", text: $searchText)
                .textFieldStyle(.roundedBorder)
            List(filteredPlayers) { player in
                Button(action: { onSelect(player.playerID) }) {
                    HStack(spacing: 12) {
                        ZStack {
                            Circle().fill(gold.opacity(0.14))
                            Text(String(player.displayName.prefix(1)))
                                .font(.system(size: 13, weight: .bold))
                                .foregroundStyle(gold)
                        }
                        .frame(width: 34, height: 34)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(player.displayName).font(.system(size: 14, weight: .semibold))
                            Text("\(player.teamName.isEmpty ? "未分队" : player.teamName) · \(player.playerID)")
                                .font(.system(size: 11))
                                .foregroundStyle(Color.secondary)
                        }
                        Spacer()
                        if selectedPlayerID == player.playerID {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(gold)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .overlay {
                if filteredPlayers.isEmpty {
                    Text("没有匹配的赛季选手").foregroundStyle(Color.secondary)
                }
            }
        }
        .padding(22)
        .frame(minWidth: 580, minHeight: 560)
    }
}

struct PhotoReviewCard: View {
    let row: ReportRow
    let imageURL: URL
    let player: ReportPlayer?
    let isManual: Bool
    let isRejected: Bool
    let onChoosePlayer: () -> Void
    let onReject: () -> Void
    let onRestore: () -> Void

    private var statusLabel: String {
        if isRejected { return "不导入" }
        if isManual { return "人工指定" }
        switch row.status {
        case "included": return row.compressionNote?.isEmpty == false ? "已压缩匹配" : "自动匹配"
        case "duplicate": return "同一选手多图"
        case "ambiguous": return "同名歧义"
        case "unmatched": return "未匹配"
        case "invalid": return "图片无效"
        case "rejected": return "未选用"
        default: return row.status
        }
    }

    private var statusColor: Color {
        if isRejected || row.status == "rejected" { return Color.gray }
        if isManual || row.status == "included" { return Color.green }
        if row.status == "invalid" { return Color.red }
        return gold
    }

    private var canAssign: Bool { row.status != "invalid" }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Group {
                if let image = NSImage(contentsOf: imageURL) {
                    Image(nsImage: image).resizable().scaledToFill()
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
            .frame(height: 172)
            .clipped()
            .overlay(alignment: .topLeading) {
                Text(statusLabel)
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(statusColor.opacity(0.88))
                    .foregroundStyle(Color.black)
                    .clipShape(Capsule())
                    .padding(8)
            }
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

            Text(row.sourceFile)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Color.white.opacity(0.88))
                .lineLimit(2)
                .truncationMode(.middle)
            if let player {
                Text("\(player.displayName) · \(player.teamName.isEmpty ? "未分队" : player.teamName)")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(isManual ? softGold : Color.white.opacity(0.7))
                    .lineLimit(1)
            } else {
                Text(row.reason.isEmpty ? "尚未指定选手" : row.reason)
                    .font(.system(size: 11))
                    .foregroundStyle(Color.white.opacity(0.56))
                    .lineLimit(2)
            }
            if !row.suggestion.isEmpty && player == nil {
                Text("可能是：\(row.suggestion)")
                    .font(.system(size: 11))
                    .foregroundStyle(softGold.opacity(0.8))
                    .lineLimit(2)
            }
            if let compressionNote = row.compressionNote, !compressionNote.isEmpty {
                Label(compressionNote, systemImage: "arrow.down.right.and.arrow.up.left")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Color.green.opacity(0.82))
                    .lineLimit(1)
            }

            HStack(spacing: 8) {
                Button(action: onChoosePlayer) {
                    Label(player == nil ? "选择选手" : "更换", systemImage: "person.crop.circle.badge.checkmark")
                }
                .buttonStyle(.bordered)
                .disabled(!canAssign)
                .help(canAssign ? "为这张图片指定当前赛季选手" : "无效图片不能导入")
                if isManual || isRejected {
                    Button(action: onRestore) { Image(systemName: "arrow.uturn.backward") }
                        .buttonStyle(.bordered)
                        .help("恢复自动匹配")
                } else if canAssign {
                    Button(action: onReject) { Image(systemName: "nosign") }
                        .buttonStyle(.bordered)
                        .help("标记为不导入")
                }
            }
        }
        .padding(11)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.22)))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isManual ? gold.opacity(0.55) : borderColor, lineWidth: isManual ? 2 : 1)
        )
    }
}

struct ContentView: View {
    @StateObject private var model = MatcherViewModel()

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.035, green: 0.035, blue: 0.035),
                    Color(red: 0.075, green: 0.065, blue: 0.045),
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
                .frame(maxWidth: 1080)
                .frame(maxWidth: .infinity)
            }
        }
        .frame(minWidth: 820, minHeight: 700)
        .preferredColorScheme(.dark)
        .onAppear { model.loadCatalogIfNeeded() }
        .sheet(isPresented: $model.isPlayerChooserPresented) {
            PlayerChooserView(
                sourceFile: model.activeSourceFile,
                players: model.rosterPlayers,
                selectedPlayerID: model.manualPlayerID(for: model.activeSourceFile)
                    ?? model.photoRows.first { $0.sourceFile == model.activeSourceFile }?.playerID,
                onSelect: { playerID in model.assignPlayer(playerID, to: model.activeSourceFile) }
            )
        }
        .alert("替换人工选择？", isPresented: $model.isAssignmentConflictPresented) {
            Button("取消", role: .cancel, action: model.cancelAssignmentReplacement)
            Button("确认替换", action: model.confirmAssignmentReplacement)
        } message: {
            Text(model.assignmentConflictMessage)
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 17) {
            ZStack {
                RoundedRectangle(cornerRadius: 12).fill(gold.opacity(0.13)).frame(width: 58, height: 58)
                RoundedRectangle(cornerRadius: 12).stroke(gold.opacity(0.46), lineWidth: 1).frame(width: 58, height: 58)
                Image(systemName: "person.crop.square")
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(softGold)
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("选手头像匹配器")
                    .font(.system(size: 29, weight: .bold, design: .rounded))
                Text("按赛事赛季读取线上名单，递归扫描图片并生成后台上传 ZIP。")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.white.opacity(0.62))
            }
        }
    }

    private var setupPanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label("匹配设置", systemImage: "slider.horizontal.3")
                    .font(.system(size: 16, weight: .semibold))
                Spacer()
                Label("递归扫描全部子文件夹", systemImage: "folder.badge.gearshape")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(softGold.opacity(0.82))
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("图片根目录")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color.white.opacity(0.72))
                HStack(spacing: 10) {
                    HStack(spacing: 9) {
                        Image(systemName: "folder").foregroundStyle(gold)
                        Text(model.folderURL?.path ?? "尚未选择")
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .foregroundStyle(model.folderURL == nil ? Color.white.opacity(0.42) : Color.white.opacity(0.88))
                    }
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.26)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(borderColor, lineWidth: 1))
                    Button(action: model.chooseFolder) {
                        Label("选择…", systemImage: "folder.badge.plus")
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(model.isRunning)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("线上赛事目录")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color.white.opacity(0.72))
                    Spacer()
                    if model.isCatalogLoading {
                        ProgressView().controlSize(.small)
                    } else {
                        Button(action: model.loadCatalog) { Image(systemName: "arrow.clockwise") }
                            .buttonStyle(.borderless)
                            .help("刷新赛事目录")
                    }
                }
                if !model.catalogError.isEmpty {
                    HStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Color.orange)
                        Text(model.catalogError)
                            .font(.system(size: 12))
                            .foregroundStyle(Color.white.opacity(0.72))
                        Spacer()
                        Button("重试", action: model.loadCatalog).buttonStyle(.bordered)
                    }
                }
                HStack(spacing: 14) {
                    VStack(alignment: .leading, spacing: 7) {
                        Text("赛事").font(.system(size: 11, weight: .medium)).foregroundStyle(Color.white.opacity(0.58))
                        Picker("赛事", selection: $model.selectedCompetitionID) {
                            Text(model.isCatalogLoading ? "正在加载…" : "请选择赛事").tag("")
                            ForEach(model.catalogCards) { competition in
                                Text(competition.displayName).tag(competition.id)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)
                        .disabled(model.isCatalogLoading || model.catalogCards.isEmpty || model.isRunning)
                        .onChange(of: model.selectedCompetitionID) { _ in model.competitionDidChange() }
                    }
                    .frame(maxWidth: .infinity)
                    VStack(alignment: .leading, spacing: 7) {
                        Text("赛季").font(.system(size: 11, weight: .medium)).foregroundStyle(Color.white.opacity(0.58))
                        Picker("赛季", selection: $model.selectedSeason) {
                            Text("请选择赛季").tag("")
                            ForEach(model.availableSeasons, id: \.self) { season in Text(season).tag(season) }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)
                        .disabled(model.selectedCompetition == nil || model.isRunning)
                        .onChange(of: model.selectedSeason) { _ in model.seasonDidChange() }
                    }
                    .frame(maxWidth: 280)
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("后台上传令牌")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color.white.opacity(0.72))
                    Spacer()
                    Button(action: model.openUploadTokenPage) {
                        Label("打开令牌页面", systemImage: "person.crop.circle.badge.key")
                    }
                    .buttonStyle(.borderless)
                    .help("在网站个人中心创建或管理上传令牌")
                }
                HStack(spacing: 10) {
                    SecureField("粘贴 wdu_ 开头的上传令牌", text: $model.uploadTokenDraft)
                        .textFieldStyle(.roundedBorder)
                        .disabled(model.isVerifyingUploadToken || model.isUploading)
                    Button(action: model.verifyAndSaveUploadToken) {
                        if model.isVerifyingUploadToken {
                            ProgressView().controlSize(.small)
                        } else {
                            Label("验证并保存", systemImage: "key.fill")
                        }
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(model.isVerifyingUploadToken || model.uploadTokenDraft.isEmpty)
                    if model.hasUploadToken {
                        Button(action: model.removeUploadToken) {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.bordered)
                        .help("从钥匙串移除上传令牌")
                    }
                }
                if !model.uploadTokenError.isEmpty {
                    Label(model.uploadTokenError, systemImage: "exclamationmark.triangle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Color.red.opacity(0.86))
                } else if !model.uploadTokenStatus.isEmpty {
                    Label(model.uploadTokenStatus, systemImage: "checkmark.shield.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Color.green.opacity(0.82))
                }
            }

            Divider().overlay(borderColor)
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.statusText)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Color.white.opacity(0.82))
                    Text("原图不会被修改；只有点击上传按钮后才会写入服务器。")
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
            }
        }
        .padding(20)
        .background(RoundedRectangle(cornerRadius: 8).fill(panel.opacity(0.94)))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(borderColor, lineWidth: 1))
    }

    private var progressPanel: some View {
        HStack(spacing: 15) {
            ProgressView().controlSize(.small).tint(gold)
            VStack(alignment: .leading, spacing: 4) {
                Text("正在处理").font(.system(size: 14, weight: .semibold))
                Text("读取完整赛季名单、递归检查图片并生成预览，图片较多时请稍候。")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.white.opacity(0.58))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(RoundedRectangle(cornerRadius: 8).fill(gold.opacity(0.08)))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(gold.opacity(0.28), lineWidth: 1))
    }

    private var errorPanel: some View {
        HStack(alignment: .top, spacing: 13) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Color(red: 0.95, green: 0.53, blue: 0.36))
                .font(.system(size: 18))
            VStack(alignment: .leading, spacing: 7) {
                Text("匹配失败").font(.system(size: 14, weight: .semibold))
                Text(model.errorText)
                    .font(.system(size: 12))
                    .foregroundStyle(Color.white.opacity(0.7))
                    .textSelection(.enabled)
                Text("检查网络、赛事赛季和图片目录后，可以再次点击“开始匹配”。")
                    .font(.system(size: 12, weight: .medium))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.red.opacity(0.08)))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.red.opacity(0.28), lineWidth: 1))
    }

    private func resultPanel(_ summary: MatcherSummary) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Label("匹配结果与人工调整", systemImage: "rectangle.and.pencil.and.ellipsis")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(softGold)
                    Text(model.reportScopeLabel)
                        .font(.system(size: 12))
                        .foregroundStyle(Color.white.opacity(0.58))
                }
                Spacer()
                Button(action: model.openPreview) {
                    Label("打开预览", systemImage: "rectangle.and.text.magnifyingglass")
                }
                .buttonStyle(SecondaryButtonStyle())
            }

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                MetricCard(value: summary.rosterCount, label: "名单选手", systemImage: "person.2", emphasized: false)
                MetricCard(value: summary.scannedCount, label: "递归扫描图片", systemImage: "folder.fill.badge.gearshape", emphasized: false)
                MetricCard(value: summary.includedCount, label: "最终收录", systemImage: "checkmark.seal", emphasized: true)
                MetricCard(value: summary.compressedCount, label: "自动压缩", systemImage: "arrow.down.right.and.arrow.up.left", emphasized: summary.compressedCount > 0)
                MetricCard(value: model.unresolvedPhotoCount, label: "需处理图片", systemImage: "questionmark.diamond", emphasized: model.unresolvedPhotoCount > 0)
                MetricCard(value: summary.invalidCount, label: "无效图片", systemImage: "exclamationmark.octagon", emphasized: summary.invalidCount > 0)
                MetricCard(value: model.manualChangeCount, label: "人工处理", systemImage: "hand.tap", emphasized: model.manualChangeCount > 0)
            }

            Divider().overlay(borderColor)
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("图片工作区").font(.system(size: 15, weight: .semibold))
                    Text("点击任意有效图片可搜索并指定当前赛季选手。")
                        .font(.system(size: 11))
                        .foregroundStyle(Color.white.opacity(0.5))
                }
                Spacer()
                Picker("图片范围", selection: $model.photoFilter) {
                    ForEach(PhotoFilter.allCases) { filter in Text(filter.rawValue).tag(filter) }
                }
                .pickerStyle(.segmented)
                .frame(width: 310)
            }

            if model.filteredPhotoRows.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.circle").font(.system(size: 25)).foregroundStyle(gold)
                    Text(model.photoFilter == .attention ? "没有待处理图片" : "当前范围没有图片")
                        .font(.system(size: 13, weight: .medium))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 28)
                .background(RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.16)))
            } else {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 3), spacing: 12) {
                    ForEach(model.filteredPhotoRows, id: \.sourceFile) { row in
                        PhotoReviewCard(
                            row: row,
                            imageURL: model.folderURL!.appendingPathComponent(row.sourceFile),
                            player: model.effectivePlayer(for: row),
                            isManual: model.manualPlayerID(for: row.sourceFile) != nil,
                            isRejected: model.rejectedSources.contains(row.sourceFile),
                            onChoosePlayer: { model.presentPlayerChooser(for: row.sourceFile) },
                            onReject: { model.markNotImported(row.sourceFile) },
                            onRestore: { model.restoreAutomatic(row.sourceFile) }
                        )
                    }
                }
            }

            Divider().overlay(borderColor)
            HStack(spacing: 10) {
                Button(action: model.revealZip) {
                    Label("在 Finder 中显示 ZIP", systemImage: "archivebox")
                }
                .buttonStyle(SecondaryButtonStyle())
                Button(action: model.openReport) {
                    Label("打开 CSV", systemImage: "tablecells")
                }
                .buttonStyle(SecondaryButtonStyle())
                Spacer()
                VStack(alignment: .trailing, spacing: 3) {
                    Text(model.manualChangeCount == 0 ? "当前使用自动匹配结果" : "有 \(model.manualChangeCount) 项人工处理")
                        .font(.system(size: 12, weight: .semibold))
                    Text("人工指定优先，同一选手最终只保留一张头像")
                        .font(.system(size: 11))
                        .foregroundStyle(Color.white.opacity(0.5))
                }
                Button(action: model.applyManualChanges) {
                    Label("应用并重新生成 ZIP", systemImage: "archivebox.fill")
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!model.canRegenerate)
            }

            Divider().overlay(borderColor)
            HStack(spacing: 14) {
                Group {
                    if model.isUploading {
                        ProgressView().controlSize(.small).tint(gold)
                    } else if !model.uploadError.isEmpty {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(Color.red.opacity(0.86))
                    } else if model.didUploadCurrentResult {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Color.green.opacity(0.86))
                    } else {
                        Image(systemName: "icloud.and.arrow.up")
                            .foregroundStyle(gold)
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("后台头像上传")
                        .font(.system(size: 13, weight: .semibold))
                    if !model.uploadError.isEmpty {
                        Text(model.uploadError)
                            .foregroundStyle(Color.red.opacity(0.86))
                    } else if !model.uploadStatus.isEmpty {
                        Text(model.uploadStatus)
                            .foregroundStyle(model.didUploadCurrentResult ? Color.green.opacity(0.86) : Color.white.opacity(0.62))
                    } else if model.isResultDirty {
                        Text("先应用人工调整并重新生成 ZIP")
                    } else if !model.hasUploadToken {
                        Text("先在上方验证并保存上传令牌")
                    } else {
                        Text("上传当前 ZIP，并等待后台导入结果")
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(Color.white.opacity(0.58))
                .lineLimit(2)
                Spacer()
                Button(action: model.uploadMatchedPhotos) {
                    Label(
                        model.isUploading ? "正在上传" : (model.didUploadCurrentResult ? "上传完成" : "上传到后台"),
                        systemImage: model.didUploadCurrentResult ? "checkmark" : "icloud.and.arrow.up.fill"
                    )
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!model.canUpload)
                .opacity(model.canUpload || model.didUploadCurrentResult ? 1 : 0.45)
            }
        }
        .padding(20)
        .background(RoundedRectangle(cornerRadius: 8).fill(panel.opacity(0.94)))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(gold.opacity(0.3), lineWidth: 1))
    }

    private var privacyNote: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "lock.shield").foregroundStyle(gold)
            Text("程序通过公开接口读取名单；上传令牌安全保存在 macOS 钥匙串，只有点击“上传到后台”后才会发送最终 ZIP。")
                .font(.system(size: 12))
                .foregroundStyle(Color.white.opacity(0.58))
        }
        .padding(.horizontal, 4)
    }
}

@main
struct PlayerPhotoMatcherApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
            .windowStyle(.titleBar)
            .commands { CommandGroup(replacing: .newItem) {} }
    }
}
