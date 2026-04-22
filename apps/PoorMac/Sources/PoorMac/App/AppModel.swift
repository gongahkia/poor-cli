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
    let id = UUID()
    let role: String
    let content: String
}

@MainActor
@Observable
final class AppModel {
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

    private var client: JSONRPCStdioClient

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

    func sendChat() async {
        guard !isBusy else { return }
        let text = chatDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        chatDraft = ""
        chatTurns.append(ChatTurn(role: "user", content: text))
        do {
            try await ensureBackend()
            let result = try await client.call(method: "poor-cli/chat", params: ["message": .string(text)])
            let content = result.objectValue?["content"]?.stringValue ?? result.prettyPrinted
            chatTurns.append(ChatTurn(role: "assistant", content: content))
            lastResult = result
        } catch {
            chatTurns.append(ChatTurn(role: "assistant", content: error.localizedDescription))
        }
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
}
