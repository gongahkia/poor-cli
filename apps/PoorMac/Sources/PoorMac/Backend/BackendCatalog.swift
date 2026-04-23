import Foundation

enum BackendArea: String, CaseIterable, Identifiable {
    case dashboard
    case conversation
    case providers
    case workspace
    case tasks
    case automation
    case sessions
    case context
    case tools
    case review
    case cost
    case diagnostics
    case delivery
    case memory
    case services
    case rpcConsole

    var id: String { rawValue }

    var title: String {
        switch self {
        case .dashboard: "Dashboard"
        case .conversation: "Conversation"
        case .providers: "Providers"
        case .workspace: "Workspace"
        case .tasks: "Tasks"
        case .automation: "Automation"
        case .sessions: "Sessions"
        case .context: "Context"
        case .tools: "Tools"
        case .review: "Review"
        case .cost: "Cost"
        case .diagnostics: "Diagnostics"
        case .delivery: "Delivery"
        case .memory: "Memory"
        case .services: "Services"
        case .rpcConsole: "RPC Console"
        }
    }

    var symbol: String {
        switch self {
        case .dashboard: "gauge.with.dots.needle.67percent"
        case .conversation: "bubble.left.and.bubble.right"
        case .providers: "cpu"
        case .workspace: "folder"
        case .tasks: "checklist"
        case .automation: "clock.arrow.circlepath"
        case .sessions: "rectangle.stack"
        case .context: "text.magnifyingglass"
        case .tools: "wrench.and.screwdriver"
        case .review: "doc.text.magnifyingglass"
        case .cost: "chart.line.uptrend.xyaxis"
        case .diagnostics: "stethoscope"
        case .delivery: "shippingbox"
        case .memory: "brain"
        case .services: "server.rack"
        case .rpcConsole: "terminal"
        }
    }
}

struct BackendAction: Identifiable, Hashable {
    let id: String
    let area: BackendArea
    let title: String
    let method: String
    let params: [String: JSONValue]
    let note: String

    init(area: BackendArea, title: String, method: String, params: [String: JSONValue] = [:], note: String = "") {
        self.id = method + ":" + title
        self.area = area
        self.title = title
        self.method = method
        self.params = params
        self.note = note
    }
}

enum BackendCatalog {
    static let actions: [BackendAction] = [
        BackendAction(area: .dashboard, title: "Startup State", method: "getStartupState"),
        BackendAction(area: .dashboard, title: "Status View", method: "poor-cli/getStatusView"),
        BackendAction(area: .dashboard, title: "Command Manifest", method: "poor-cli/getCommandManifest"),
        BackendAction(area: .providers, title: "List Providers", method: "poor-cli/listProviders"),
        BackendAction(area: .providers, title: "Provider Info", method: "poor-cli/getProviderInfo"),
        BackendAction(area: .providers, title: "API Key Status", method: "poor-cli/getApiKeyStatus"),
        BackendAction(area: .providers, title: "Ollama Models", method: "poor-cli/listOllamaModels"),
        BackendAction(area: .workspace, title: "Trust Status", method: "poor-cli/getTrustStatus"),
        BackendAction(area: .workspace, title: "Trust View", method: "poor-cli/getTrustView"),
        BackendAction(area: .workspace, title: "Policy Status", method: "poor-cli/getPolicyStatus"),
        BackendAction(area: .workspace, title: "Sandbox Status", method: "poor-cli/getSandboxStatus"),
        BackendAction(area: .tasks, title: "List Tasks", method: "poor-cli/listTasks"),
        BackendAction(area: .tasks, title: "Create Task Draft", method: "poor-cli/createTask", params: [
            "title": .string("New Mac task"),
            "prompt": .string("Describe the task."),
            "autoStart": .bool(false),
        ]),
        BackendAction(area: .automation, title: "List Automations", method: "poor-cli/listAutomations"),
        BackendAction(area: .automation, title: "Run Due Automations", method: "poor-cli/runDueAutomations"),
        BackendAction(area: .automation, title: "List Workflows", method: "poor-cli/listWorkflows"),
        BackendAction(area: .sessions, title: "List Sessions", method: "poor-cli/listSessions"),
        BackendAction(area: .sessions, title: "List History", method: "poor-cli/listHistory"),
        BackendAction(area: .sessions, title: "List Mux Sessions", method: "poor-cli/listMuxSessions"),
        BackendAction(area: .context, title: "Context Snapshot", method: "context.snapshot"),
        BackendAction(area: .context, title: "Context Refresh", method: "context.refresh"),
        BackendAction(area: .context, title: "Context Pressure", method: "poor-cli/getContextPressure"),
        BackendAction(area: .context, title: "Index Stats", method: "poor-cli/getIndexStats"),
        BackendAction(area: .context, title: "Repo Map Top", method: "repo_map.top"),
        BackendAction(area: .tools, title: "Visible Tools", method: "poor-cli/getTools"),
        BackendAction(area: .tools, title: "Get Completion", method: "poor-cli/getCompletion", params: ["prefix": .string("")]),
        BackendAction(area: .tools, title: "Timeline", method: "timeline.list"),
        BackendAction(area: .review, title: "Diff List", method: "diff.list"),
        BackendAction(area: .review, title: "Pending Edits", method: "poor-cli/listPendingEdits"),
        BackendAction(area: .cost, title: "Cost Summary", method: "poor-cli/costSummary"),
        BackendAction(area: .cost, title: "Cost History", method: "cost.history"),
        BackendAction(area: .cost, title: "Budget Templates", method: "poor-cli/listBudgetTemplates"),
        BackendAction(area: .cost, title: "Economy Savings", method: "poor-cli/getEconomySavings"),
        BackendAction(area: .diagnostics, title: "Doctor Report", method: "poor-cli/getDoctorReport"),
        BackendAction(area: .diagnostics, title: "MCP Status", method: "poor-cli/getMcpStatus"),
        BackendAction(area: .diagnostics, title: "MCP Health", method: "mcp.health"),
        BackendAction(area: .diagnostics, title: "Recovery Suggestions", method: "poor-cli/getRecoverySuggestions"),
        BackendAction(area: .delivery, title: "Deploy Targets", method: "poor-cli/deployTargets"),
        BackendAction(area: .delivery, title: "Deploy History", method: "poor-cli/deployHistory"),
        BackendAction(area: .delivery, title: "Checkpoints", method: "poor-cli/listCheckpoints"),
        BackendAction(area: .memory, title: "List Memory", method: "poor-cli/memoryList"),
        BackendAction(area: .memory, title: "Search Memory", method: "poor-cli/memorySearch", params: ["query": .string("")]),
        BackendAction(area: .memory, title: "Memory Review", method: "poor-cli/memoryReviewList"),
        BackendAction(area: .services, title: "Service Status", method: "poor-cli/getServiceStatus"),
        BackendAction(area: .services, title: "Service Logs", method: "poor-cli/getServiceLogs"),
    ]

    static func actions(for area: BackendArea) -> [BackendAction] {
        actions.filter { $0.area == area }
    }
}
