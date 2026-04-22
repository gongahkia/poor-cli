import Foundation

struct JSONRPCFraming {
    static let delimiter = Data("\r\n\r\n".utf8)

    static func frame(_ body: Data) -> Data {
        var data = Data("Content-Length: \(body.count)\r\n\r\n".utf8)
        data.append(body)
        return data
    }

    static func contentLength(from header: Data) throws -> Int {
        guard let headerText = String(data: header, encoding: .ascii) else {
            throw BackendClientError.invalidHeader
        }
        let lengthLine = headerText
            .components(separatedBy: "\r\n")
            .first { $0.lowercased().hasPrefix("content-length:") }
        guard let lengthText = lengthLine?.split(separator: ":", maxSplits: 1).last,
              let length = Int(lengthText.trimmingCharacters(in: .whitespacesAndNewlines)),
              length > 0
        else {
            throw BackendClientError.invalidLength
        }
        return length
    }
}

struct BackendConfiguration: Equatable, Sendable {
    var repoRoot: String
    var pythonExecutable: String
    var provider: String
    var model: String
    var apiKey: String
    var permissionMode: String
    var sandboxPreset: String
    var validateAPIKey: Bool

    static func detected() -> BackendConfiguration {
        let fileManager = FileManager.default
        let env = ProcessInfo.processInfo.environment
        let cwd = URL(fileURLWithPath: fileManager.currentDirectoryPath)
        var candidates = [URL]()
        if let explicit = env["POOR_CLI_REPO"], !explicit.isEmpty {
            candidates.append(URL(fileURLWithPath: explicit))
        }
        candidates.append(cwd)
        candidates.append(cwd.deletingLastPathComponent().deletingLastPathComponent())

        var source = URL(fileURLWithPath: #filePath)
        for _ in 0..<8 {
            source.deleteLastPathComponent()
            candidates.append(source)
        }

        let root = candidates.first { candidate in
            fileManager.fileExists(atPath: candidate.appendingPathComponent("pyproject.toml").path)
        } ?? cwd
        let venvPython = root.appendingPathComponent(".venv/bin/python").path
        let python = fileManager.isExecutableFile(atPath: venvPython) ? venvPython : "/usr/bin/env"
        return BackendConfiguration(
            repoRoot: root.path,
            pythonExecutable: python,
            provider: "",
            model: "",
            apiKey: "",
            permissionMode: "default",
            sandboxPreset: "workspace-write",
            validateAPIKey: false
        )
    }

    var launchURL: URL {
        URL(fileURLWithPath: pythonExecutable)
    }

    var launchArguments: [String] {
        if pythonExecutable == "/usr/bin/env" {
            ["python3", "-m", "poor_cli.server", "--stdio"]
        } else {
            ["-m", "poor_cli.server", "--stdio"]
        }
    }

    var initializeParams: [String: JSONValue] {
        var params: [String: JSONValue] = [
            "clientCapabilities": .object([
                "macOSNativeApp": .bool(true),
                "settingsScene": .bool(true),
                "rpcConsole": .bool(true),
                "streaming": .bool(true),
            ]),
            "permissionMode": .string(permissionMode),
            "sandboxPreset": .string(sandboxPreset),
            "streaming": .bool(true),
            "validateApiKey": .bool(validateAPIKey),
        ]
        if !provider.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            params["provider"] = .string(provider)
        }
        if !model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            params["model"] = .string(model)
        }
        if !apiKey.isEmpty {
            params["apiKey"] = .string(apiKey)
        }
        return params
    }
}

struct JSONRPCErrorPayload: Codable, Error, Sendable {
    let code: Int
    let message: String
    let data: JSONValue?
}

private struct JSONRPCRequest: Encodable {
    let jsonrpc = "2.0"
    let id: Int
    let method: String
    let params: [String: JSONValue]
}

private struct JSONRPCNotification: Encodable {
    let jsonrpc = "2.0"
    let method: String
    let params: [String: JSONValue]
}

struct JSONRPCNotificationEvent: Sendable {
    let method: String
    let params: [String: JSONValue]
}

struct JSONRPCOutboundNotification: Sendable {
    let method: String
    let params: [String: JSONValue]
}

private struct JSONRPCResponse: Decodable {
    let jsonrpc: String?
    let id: Int?
    let method: String?
    let params: [String: JSONValue]?
    let result: JSONValue?
    let error: JSONRPCErrorPayload?
}

enum BackendClientError: LocalizedError {
    case processNotRunning
    case launchFailed(String)
    case invalidHeader
    case invalidLength
    case eof
    case invalidParameterJSON
    case processExited(code: Int32, stderr: String)
    case responseMismatch(expected: Int, got: Int?)

    var errorDescription: String? {
        switch self {
        case .processNotRunning:
            "Backend process is not running."
        case .launchFailed(let message):
            "Backend launch failed: \(message)"
        case .invalidHeader:
            "Backend returned an invalid JSON-RPC header."
        case .invalidLength:
            "Backend returned an invalid Content-Length."
        case .eof:
            "Backend closed stdout."
        case .invalidParameterJSON:
            "RPC params must be a JSON object."
        case .processExited(let code, let stderr):
            "Backend exited with code \(code).\(stderr.isEmpty ? "" : "\n\(stderr)")"
        case .responseMismatch(let expected, let got):
            "Backend response id mismatch. Expected \(expected), got \(got.map(String.init) ?? "nil")."
        }
    }
}

final class StderrBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()
    private let limit = 64 * 1024

    func append(_ newData: Data) {
        guard !newData.isEmpty else { return }
        lock.lock()
        data.append(newData)
        if data.count > limit {
            data.removeFirst(data.count - limit)
        }
        lock.unlock()
    }

    func text() -> String {
        lock.lock()
        let snapshot = data
        lock.unlock()
        return String(data: snapshot, encoding: .utf8) ?? ""
    }

    func reset() {
        lock.lock()
        data.removeAll(keepingCapacity: true)
        lock.unlock()
    }
}

actor JSONRPCStdioClient {
    private var configuration: BackendConfiguration
    private var process: Process?
    private var stdin: FileHandle?
    private var stdout: FileHandle?
    private var stderr: FileHandle?
    private let stderrBuffer = StderrBuffer()
    private var nextID = 1

    init(configuration: BackendConfiguration) {
        self.configuration = configuration
    }

    var isRunning: Bool {
        process?.isRunning == true
    }

    func updateConfiguration(_ configuration: BackendConfiguration) {
        if self.configuration != configuration {
            stop()
        }
        self.configuration = configuration
    }

    func start() throws {
        if process?.isRunning == true { return }
        guard FileManager.default.fileExists(atPath: configuration.repoRoot) else {
            throw BackendClientError.launchFailed("Repository root does not exist: \(configuration.repoRoot)")
        }

        let inputPipe = Pipe()
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        let launched = Process()
        launched.executableURL = configuration.launchURL
        launched.arguments = configuration.launchArguments
        launched.currentDirectoryURL = URL(fileURLWithPath: configuration.repoRoot)
        launched.standardInput = inputPipe
        launched.standardOutput = outputPipe
        launched.standardError = errorPipe
        stderrBuffer.reset()
        errorPipe.fileHandleForReading.readabilityHandler = { [stderrBuffer] handle in
            stderrBuffer.append(handle.availableData)
        }

        do {
            try launched.run()
        } catch {
            throw BackendClientError.launchFailed(error.localizedDescription)
        }

        process = launched
        stdin = inputPipe.fileHandleForWriting
        stdout = outputPipe.fileHandleForReading
        stderr = errorPipe.fileHandleForReading
    }

    func stop() {
        stderr?.readabilityHandler = nil
        try? stdin?.close()
        if process?.isRunning == true {
            process?.terminate()
        }
        process = nil
        stdin = nil
        stdout = nil
        stderr = nil
    }

    func initialize() async throws -> JSONValue {
        try await call(method: "initialize", params: configuration.initializeParams)
    }

    func shutdownIfRunning() async {
        guard process?.isRunning == true else {
            stop()
            return
        }
        do {
            _ = try await call(method: "shutdown", params: [:], autoStart: false, onNotification: nil)
        } catch {
            // termination below is the fallback path
        }
        stop()
    }

    func call(method: String, params: [String: JSONValue] = [:]) async throws -> JSONValue {
        try await call(method: method, params: params, autoStart: true, onNotification: nil)
    }

    func call(
        method: String,
        params: [String: JSONValue] = [:],
        onNotification: (@Sendable (JSONRPCNotificationEvent) async -> JSONRPCOutboundNotification?)?
    ) async throws -> JSONValue {
        try await call(method: method, params: params, autoStart: true, onNotification: onNotification)
    }

    func notify(method: String, params: [String: JSONValue] = [:]) async throws {
        try start()
        try writeNotification(JSONRPCOutboundNotification(method: method, params: params))
    }

    private func call(
        method: String,
        params: [String: JSONValue],
        autoStart: Bool,
        onNotification: (@Sendable (JSONRPCNotificationEvent) async -> JSONRPCOutboundNotification?)?
    ) async throws -> JSONValue {
        if autoStart {
            try start()
        }
        try throwIfExited()
        let id = nextID
        nextID += 1
        let request = JSONRPCRequest(id: id, method: method, params: params)
        let body = try JSONEncoder().encode(request)
        guard let stdin else { throw BackendClientError.processNotRunning }
        stdin.write(JSONRPCFraming.frame(body))

        while true {
            try throwIfExited()
            let response = try readResponse()
            if let method = response.method, response.id == nil {
                if let outbound = await onNotification?(JSONRPCNotificationEvent(
                    method: method,
                    params: response.params ?? [:]
                )) {
                    try writeNotification(outbound)
                }
                continue
            }
            guard response.id == id else {
                throw BackendClientError.responseMismatch(expected: id, got: response.id)
            }
            if let error = response.error {
                throw error
            }
            return response.result ?? .null
        }
    }

    private func writeNotification(_ notification: JSONRPCOutboundNotification) throws {
        let payload = JSONRPCNotification(method: notification.method, params: notification.params)
        let body = try JSONEncoder().encode(payload)
        guard let stdin else { throw BackendClientError.processNotRunning }
        stdin.write(JSONRPCFraming.frame(body))
    }

    private func throwIfExited() throws {
        if let process, !process.isRunning, process.terminationReason == .exit {
            throw BackendClientError.processExited(
                code: process.terminationStatus,
                stderr: stderrBuffer.text()
            )
        }
    }

    private func readResponse() throws -> JSONRPCResponse {
        guard let stdout else { throw BackendClientError.processNotRunning }
        var header = Data()
        let delimiter = JSONRPCFraming.delimiter
        while header.count < delimiter.count || header.suffix(delimiter.count) != delimiter {
            let byte = stdout.readData(ofLength: 1)
            if byte.isEmpty { throw BackendClientError.eof }
            header.append(byte)
            if header.count > 8192 { throw BackendClientError.invalidHeader }
        }
        let length = try JSONRPCFraming.contentLength(from: header)
        let body = stdout.readData(ofLength: length)
        if body.count != length { throw BackendClientError.eof }
        return try JSONDecoder().decode(JSONRPCResponse.self, from: body)
    }
}
