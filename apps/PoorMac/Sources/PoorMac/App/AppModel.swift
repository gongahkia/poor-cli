import Foundation
import Observation

enum ConnectionState: Equatable {
    case stopped
    case starting
    case connected
    case failed(String)

    var title: String {
        switch self {
        case .stopped: "Stopped"
        case .starting: "Starting"
        case .connected: "Connected"
        case .failed: "Failed"
        }
    }
}

struct AppLogLine: Identifiable, Hashable {
    let id = UUID()
    let date = Date()
    let title: String
    let detail: String
}

struct ChatTurn: Identifiable, Hashable {
    let id: UUID
    let role: String
    var content: String

    init(id: UUID = UUID(), role: String, content: String) {
        self.id = id
        self.role = role
        self.content = content
    }
}

struct StreamEventLine: Identifiable, Hashable {
    let id = UUID()
    let title: String
    let detail: String
    let symbol: String
}

struct DomainRecord: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let detail: String
}

struct PendingPermissionReview: Identifiable, Hashable {
    let id: String
    let toolName: String
    let operation: String
    let message: String
    let paths: [String]
    let diff: String
    let payload: [String: JSONValue]
}

struct PendingPlanReview: Identifiable, Hashable {
    let id: String
    let summary: String
    let originalRequest: String
    let steps: [String]
    let payload: [String: JSONValue]
}

enum PendingReviewSheet: Identifiable, Hashable {
    case permission(PendingPermissionReview)
    case plan(PendingPlanReview)

    var id: String {
        switch self {
        case .permission(let review): "permission-\(review.id)"
        case .plan(let review): "plan-\(review.id)"
        }
    }
}

@MainActor
@Observable
final class AppModel: @unchecked Sendable {
    var selectedArea: BackendArea = .dashboard
    var configuration = BackendConfiguration.detected()
    var connectionState: ConnectionState = .stopped
    var lastResult: JSONValue = .object([:])
    var logs: [AppLogLine] = []
    var chatTurns: [ChatTurn] = []
    var chatDraft = ""
    var execDraft = ""
    var rpcMethod = "getStartupState"
    var rpcParamsText = "{}"
    var discoveredMethods: [String] = []
    var isBusy = false
    var keychainStatus = ""
    var streamEvents: [StreamEventLine] = []
    var pendingReviewSheet: PendingReviewSheet?
    var activeRequestID: String?
    var domainRecords: [BackendArea: [DomainRecord]] = [:]
    var selectedDomainRecordID: String?

    private var client: JSONRPCStdioClient
    @ObservationIgnored private var reviewContinuation: CheckedContinuation<Bool, Never>?

    init() {
        let configuration = BackendConfiguration.detected()
        self.configuration = configuration
        self.client = JSONRPCStdioClient(configuration: configuration)
        self.discoveredMethods = Self.loadRegistryMethods(repoRoot: configuration.repoRoot)
    }

    var statusDetail: String {
        switch connectionState {
        case .failed(let message):
            message
        default:
            configuration.repoRoot
        }
    }

    func startBackend() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await connectBackend()
        } catch {
            // connectBackend records the user-visible failure
        }
    }

    private func connectBackend() async throws {
        connectionState = .starting
        do {
            if configuration.apiKey.isEmpty,
               let apiKey = try? KeychainStore.readAPIKey(provider: configuration.provider),
               !apiKey.isEmpty {
                configuration.apiKey = apiKey
                keychainStatus = "Loaded API key from Keychain."
            }
            await client.updateConfiguration(configuration)
            try await client.start()
            let result = try await client.initialize()
            lastResult = result
            connectionState = .connected
            appendLog("Backend initialized", result.prettyPrinted)
            discoveredMethods = Self.loadRegistryMethods(repoRoot: configuration.repoRoot)
        } catch {
            connectionState = .failed(error.localizedDescription)
            appendLog("Backend start failed", error.localizedDescription)
            throw error
        }
    }

    func stopBackend() async {
        await client.shutdownIfRunning()
        connectionState = .stopped
        appendLog("Backend stopped", configuration.repoRoot)
    }

    func runAction(_ action: BackendAction) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await ensureBackend()
            let result = try await client.call(method: action.method, params: action.params)
            lastResult = result
            appendLog(action.title, result.prettyPrinted)
        } catch {
            lastResult = .object(["error": .string(error.localizedDescription)])
            appendLog(action.title + " failed", error.localizedDescription)
        }
    }

    @discardableResult
    func callBackend(
        method: String,
        params: [String: JSONValue] = [:],
        title: String? = nil
    ) async -> JSONValue? {
        guard !isBusy else { return nil }
        isBusy = true
        defer { isBusy = false }
        do {
            try await ensureBackend()
            let result = try await client.call(method: method, params: params)
            lastResult = result
            appendLog(title ?? method, result.prettyPrinted)
            return result
        } catch {
            lastResult = .object(["error": .string(error.localizedDescription)])
            appendLog((title ?? method) + " failed", error.localizedDescription)
            return nil
        }
    }

    func loadDomain(area: BackendArea, action: BackendAction) async {
        guard let result = await callBackend(method: action.method, params: action.params, title: action.title) else {
            return
        }
        domainRecords[area] = Self.records(from: result, fallbackTitle: action.title)
    }

    func sendChat() async {
        guard !isBusy else { return }
        let text = chatDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        chatDraft = ""
        chatTurns.append(ChatTurn(role: "user", content: text))
        let assistantID = UUID()
        chatTurns.append(ChatTurn(id: assistantID, role: "assistant", content: ""))
        do {
            try await ensureBackend()
            let requestID = "mac-\(UUID().uuidString)"
            activeRequestID = requestID
            let result = try await client.call(
                method: "poor-cli/chatStreaming",
                params: [
                    "message": .string(text),
                    "requestId": .string(requestID),
                ],
                onNotification: { [weak self] event in
                    await self?.handleStreamingNotification(event, assistantID: assistantID)
                }
            )
            let content = result.objectValue?["content"]?.stringValue ?? result.prettyPrinted
            replaceChatTurn(id: assistantID, content: content)
            lastResult = result
            activeRequestID = nil
        } catch {
            replaceChatTurn(id: assistantID, content: error.localizedDescription)
            activeRequestID = nil
        }
    }

    func cancelActiveRequest() async {
        guard let activeRequestID else { return }
        do {
            try await client.notify(method: "poor-cli/cancelRequest", params: [
                "requestId": .string(activeRequestID),
            ])
            appendStreamEvent("Cancelled", activeRequestID, symbol: "xmark.circle")
        } catch {
            appendStreamEvent("Cancel failed", error.localizedDescription, symbol: "exclamationmark.triangle")
        }
        self.activeRequestID = nil
    }

    func runExec() async {
        guard !isBusy else { return }
        let text = execDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await ensureBackend()
            let result = try await client.call(method: "poor-cli/exec", params: [
                "prompt": .string(text),
                "outputFormat": .string("text"),
            ])
            lastResult = result
            appendLog("Exec", result.prettyPrinted)
        } catch {
            lastResult = .object(["error": .string(error.localizedDescription)])
            appendLog("Exec failed", error.localizedDescription)
        }
    }

    func runRPCConsole() async {
        guard !isBusy else { return }
        let method = rpcMethod.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !method.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await ensureBackend()
            let params = try decodeParams(rpcParamsText)
            let result = try await client.call(method: method, params: params)
            lastResult = result
            appendLog(method, result.prettyPrinted)
        } catch {
            lastResult = .object(["error": .string(error.localizedDescription)])
            appendLog(method + " failed", error.localizedDescription)
        }
    }

    func refreshRegistry() {
        discoveredMethods = Self.loadRegistryMethods(repoRoot: configuration.repoRoot)
    }

    func loadAPIKeyFromKeychain() {
        do {
            if let apiKey = try KeychainStore.readAPIKey(provider: configuration.provider) {
                configuration.apiKey = apiKey
                keychainStatus = "Loaded API key from Keychain."
            } else {
                keychainStatus = "No API key found in Keychain."
            }
        } catch {
            keychainStatus = error.localizedDescription
        }
    }

    func saveAPIKeyToKeychain() {
        do {
            try KeychainStore.saveAPIKey(configuration.apiKey, provider: configuration.provider)
            keychainStatus = "Saved API key to Keychain."
        } catch {
            keychainStatus = error.localizedDescription
        }
    }

    func deleteAPIKeyFromKeychain() {
        do {
            try KeychainStore.deleteAPIKey(provider: configuration.provider)
            configuration.apiKey = ""
            keychainStatus = "Deleted API key from Keychain."
        } catch {
            keychainStatus = error.localizedDescription
        }
    }

    func setProviderAPIKey() async {
        let provider = configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines)
        let apiKey = configuration.apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !provider.isEmpty, !apiKey.isEmpty else {
            keychainStatus = "Provider and API key are required."
            return
        }
        _ = await callBackend(
            method: "poor-cli/setApiKey",
            params: [
                "provider": .string(provider),
                "apiKey": .string(apiKey),
                "persist": .bool(true),
                "reloadActiveProvider": .bool(true),
            ],
            title: "Set API key"
        )
    }

    func testProviderAPIKey() async {
        let provider = configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !provider.isEmpty else {
            keychainStatus = "Provider is required."
            return
        }
        _ = await callBackend(
            method: "poor-cli/testApiKey",
            params: [
                "provider": .string(provider),
                "apiKey": .string(configuration.apiKey),
            ],
            title: "Test API key"
        )
    }

    func switchProviderFromSettings() async {
        let provider = configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !provider.isEmpty else { return }
        var params: [String: JSONValue] = ["provider": .string(provider)]
        let model = configuration.model.trimmingCharacters(in: .whitespacesAndNewlines)
        if !model.isEmpty {
            params["model"] = .string(model)
        }
        _ = await callBackend(method: "poor-cli/switchProvider", params: params, title: "Switch provider")
    }

    func resolvePendingReview(allowed: Bool) {
        pendingReviewSheet = nil
        reviewContinuation?.resume(returning: allowed)
        reviewContinuation = nil
    }

    private func ensureBackend() async throws {
        if connectionState != .connected {
            try await connectBackend()
        }
        if case .failed(let message) = connectionState {
            throw BackendClientError.launchFailed(message)
        }
    }

    private func appendLog(_ title: String, _ detail: String) {
        logs.insert(AppLogLine(title: title, detail: detail), at: 0)
        if logs.count > 200 {
            logs.removeLast(logs.count - 200)
        }
    }

    private func appendStreamEvent(_ title: String, _ detail: String, symbol: String) {
        streamEvents.insert(StreamEventLine(title: title, detail: detail, symbol: symbol), at: 0)
        if streamEvents.count > 100 {
            streamEvents.removeLast(streamEvents.count - 100)
        }
    }

    private func appendChatTurn(id: UUID, chunk: String) {
        guard let index = chatTurns.firstIndex(where: { $0.id == id }) else { return }
        chatTurns[index].content += chunk
    }

    private func replaceChatTurn(id: UUID, content: String) {
        guard let index = chatTurns.firstIndex(where: { $0.id == id }) else { return }
        chatTurns[index].content = content
    }

    func handleStreamingNotification(
        _ event: JSONRPCNotificationEvent,
        assistantID: UUID
    ) async -> JSONRPCOutboundNotification? {
        switch event.method {
        case "poor-cli/streamChunk":
            let chunk = event.params["chunk"]?.stringValue ?? ""
            let done = event.params["done"] == .bool(true)
            if !chunk.isEmpty {
                appendChatTurn(id: assistantID, chunk: chunk)
            }
            if done {
                appendStreamEvent("Response complete", event.params["reason"]?.stringValue ?? "complete", symbol: "checkmark.circle")
            }
        case "poor-cli/thinkingChunk":
            appendStreamEvent("Thinking", event.params["chunk"]?.stringValue ?? "", symbol: "brain")
        case "poor-cli/toolEvent":
            let toolName = event.params["toolName"]?.stringValue ?? "tool"
            let eventType = event.params["eventType"]?.stringValue ?? "event"
            appendStreamEvent(toolName, eventType, symbol: "wrench.and.screwdriver")
        case "tool.chunk":
            let toolName = event.params["toolName"]?.stringValue ?? "tool"
            appendStreamEvent(toolName, event.params["chunk"]?.stringValue ?? "", symbol: "terminal")
            if let eventID = event.params["eventId"]?.stringValue {
                let chunkIndex = event.params["chunkIndex"]?.intValue ?? 0
                return JSONRPCOutboundNotification(method: "poor-cli/toolStreamAck", params: [
                    "eventId": .string(eventID),
                    "chunksProcessed": .number(Double(chunkIndex + 1)),
                ])
            }
        case "poor-cli/progress":
            appendStreamEvent(
                event.params["phase"]?.stringValue ?? "Progress",
                event.params["message"]?.stringValue ?? "",
                symbol: "arrow.clockwise"
            )
        case "poor-cli/costUpdate":
            appendStreamEvent("Cost update", JSONValue.object(event.params).prettyPrinted, symbol: "chart.line.uptrend.xyaxis")
        case "poor-cli/contextPressure":
            appendStreamEvent("Context pressure", JSONValue.object(event.params).prettyPrinted, symbol: "text.magnifyingglass")
        case "poor-cli/economyTurnReport":
            appendStreamEvent("Economy", JSONValue.object(event.params).prettyPrinted, symbol: "banknote")
        case "poor-cli/permissionReq":
            let allowed = await reviewPermission(event.params)
            return JSONRPCOutboundNotification(method: "poor-cli/permissionRes", params: [
                "promptId": event.params["promptId"] ?? .string(""),
                "allowed": .bool(allowed),
                "approvedPaths": .array([]),
                "approvedChunks": .array([]),
            ])
        case "poor-cli/planReq":
            let allowed = await reviewPlan(event.params)
            return JSONRPCOutboundNotification(method: "poor-cli/planRes", params: [
                "promptId": event.params["promptId"] ?? .string(""),
                "allowed": .bool(allowed),
            ])
        default:
            appendStreamEvent(event.method, JSONValue.object(event.params).prettyPrinted, symbol: "bell")
        }
        return nil
    }

    private func reviewPermission(_ params: [String: JSONValue]) async -> Bool {
        await withCheckedContinuation { continuation in
            reviewContinuation = continuation
            pendingReviewSheet = .permission(PendingPermissionReview(
                id: params["promptId"]?.stringValue ?? UUID().uuidString,
                toolName: params["toolName"]?.stringValue ?? "Tool",
                operation: params["operation"]?.stringValue ?? "",
                message: params["message"]?.stringValue ?? "",
                paths: params["paths"]?.arrayValue?.compactMap(\.stringValue) ?? [],
                diff: params["diff"]?.stringValue ?? "",
                payload: params
            ))
        }
    }

    private func reviewPlan(_ params: [String: JSONValue]) async -> Bool {
        await withCheckedContinuation { continuation in
            reviewContinuation = continuation
            let rawSteps = params["steps"]?.arrayValue ?? []
            pendingReviewSheet = .plan(PendingPlanReview(
                id: params["promptId"]?.stringValue ?? UUID().uuidString,
                summary: params["summary"]?.stringValue ?? "",
                originalRequest: params["originalRequest"]?.stringValue ?? "",
                steps: rawSteps.map(\.prettyPrinted),
                payload: params
            ))
        }
    }

    private func decodeParams(_ text: String) throws -> [String: JSONValue] {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [:] }
        let data = Data(trimmed.utf8)
        let value = try JSONDecoder().decode(JSONValue.self, from: data)
        guard let object = value.objectValue else {
            throw BackendClientError.invalidParameterJSON
        }
        return object
    }

    private static func loadRegistryMethods(repoRoot: String) -> [String] {
        let url = URL(fileURLWithPath: repoRoot)
            .appendingPathComponent("poor_cli/server/registry_static_index.json")
        guard let data = try? Data(contentsOf: url),
              let value = try? JSONDecoder().decode(JSONValue.self, from: data),
              let rpcIndex = value.objectValue?["rpcIndex"]?.objectValue
        else {
            return []
        }
        return rpcIndex.keys.sorted()
    }

    private static func records(from value: JSONValue, fallbackTitle: String) -> [DomainRecord] {
        if let object = value.objectValue {
            for key in ["edits", "tasks", "automations", "sessions", "history", "checkpoints", "memories", "services", "tools", "providers", "models", "runs", "workflows"] {
                if let array = object[key]?.arrayValue {
                    return array.enumerated().map { index, value in
                        record(from: value, id: "\(key)-\(index)", fallbackTitle: key)
                    }
                }
            }
            if let providers = object["providers"]?.objectValue {
                return providers.keys.sorted().map { key in
                    record(from: providers[key] ?? .object([:]), id: key, fallbackTitle: key)
                }
            }
            if object.keys.count > 1 {
                return object.keys.sorted().map { key in
                    record(from: object[key] ?? .null, id: key, fallbackTitle: key)
                }
            }
        }
        return [record(from: value, id: fallbackTitle, fallbackTitle: fallbackTitle)]
    }

    private static func record(from value: JSONValue, id: String, fallbackTitle: String) -> DomainRecord {
        if let object = value.objectValue {
            let title = firstString(object, keys: ["title", "name", "id", "taskId", "automationId", "sessionId", "path", "provider", "status"]) ?? fallbackTitle
            let subtitle = firstString(object, keys: ["status", "state", "kind", "source", "method", "summary", "label"]) ?? ""
            return DomainRecord(
                id: firstString(object, keys: ["id", "taskId", "automationId", "sessionId", "editId", "checkpointId"]) ?? id,
                title: title,
                subtitle: subtitle,
                detail: value.prettyPrinted
            )
        }
        return DomainRecord(id: id, title: fallbackTitle, subtitle: "", detail: value.prettyPrinted)
    }

    private static func firstString(_ object: [String: JSONValue], keys: [String]) -> String? {
        for key in keys {
            if let string = object[key]?.stringValue, !string.isEmpty {
                return string
            }
            if let number = object[key]?.intValue {
                return String(number)
            }
        }
        return nil
    }
}
