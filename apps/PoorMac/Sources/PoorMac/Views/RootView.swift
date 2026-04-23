import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var app
    @SceneStorage("PoorMac.selectedArea") private var selectedAreaRaw = BackendArea.dashboard.rawValue

    var body: some View {
        NavigationSplitView {
            List(BackendArea.allCases, selection: selectionBinding) { area in
                Label(area.title, systemImage: area.symbol)
                    .accessibilityIdentifier("PoorMac.Sidebar.\(area.rawValue)")
                    .tag(area)
            }
            .accessibilityIdentifier("PoorMac.Sidebar")
            .navigationTitle("PoorMac")
            .navigationSplitViewColumnWidth(min: 220, ideal: 250, max: 320)
        } detail: {
            DetailRouter(area: selectedArea)
                .navigationTitle(selectedArea.title)
                .toolbar {
                    ToolbarItemGroup {
                        StatusBadge(state: app.connectionState)
                        if app.isBusy {
                            ProgressView()
                                .controlSize(.small)
                        }
                        Button {
                            Task { await app.startBackend() }
                        } label: {
                            Label("Start Backend", systemImage: "play.fill")
                        }
                        .labelStyle(.iconOnly)
                        .help("Start Backend")
                        .accessibilityIdentifier("PoorMac.Toolbar.StartBackend")
                        .disabled(app.isBusy)
                        Button {
                            Task { await app.stopBackend() }
                        } label: {
                            Label("Stop Backend", systemImage: "stop.fill")
                        }
                        .labelStyle(.iconOnly)
                        .help("Stop Backend")
                        .accessibilityIdentifier("PoorMac.Toolbar.StopBackend")
                        Button {
                            Task { await app.cancelActiveRequest() }
                        } label: {
                            Label("Cancel Request", systemImage: "xmark.circle")
                        }
                        .labelStyle(.iconOnly)
                        .help("Cancel Request")
                        .accessibilityIdentifier("PoorMac.Toolbar.CancelRequest")
                        .disabled(app.activeRequestID == nil)
                    }
                }
                .sheet(item: reviewSheetBinding) { sheet in
                    ReviewSheetView(sheet: sheet)
                        .environment(app)
                }
        }
        .navigationSplitViewStyle(.balanced)
    }

    private var selectionBinding: Binding<BackendArea?> {
        Binding(
            get: { selectedArea },
            set: { selectedAreaRaw = ($0 ?? .dashboard).rawValue }
        )
    }

    private var selectedArea: BackendArea {
        BackendArea(rawValue: selectedAreaRaw) ?? .dashboard
    }

    private var reviewSheetBinding: Binding<PendingReviewSheet?> {
        Binding(
            get: { app.pendingReviewSheet },
            set: { app.pendingReviewSheet = $0 }
        )
    }
}

private struct DetailRouter: View {
    let area: BackendArea

    var body: some View {
        switch area {
        case .dashboard:
            DashboardView()
        case .conversation:
            ConversationView()
        case .providers:
            ProviderSurfaceView()
        case .tasks:
            TaskSurfaceView()
        case .automation:
            AutomationSurfaceView()
        case .diagnostics:
            DiagnosticsSurfaceView()
        case .cost:
            CostSurfaceView()
        case .review:
            DiffReviewView()
        case .sessions, .context, .tools, .delivery, .memory, .services, .workspace:
            DomainSurfaceView(
                area: area,
                primaryAction: BackendCatalog.primaryAction(for: area),
                actions: BackendCatalog.actions(for: area)
            )
        case .rpcConsole:
            RPCConsoleView()
        }
    }
}

private struct ReviewSheetView: View {
    @Environment(AppModel.self) private var app
    let sheet: PendingReviewSheet

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            switch sheet {
            case .permission(let review):
                Label(review.toolName, systemImage: "lock.shield")
                    .font(.title3)
                if !review.operation.isEmpty {
                    Text(review.operation)
                        .foregroundStyle(.secondary)
                }
                if !review.message.isEmpty {
                    Text(review.message)
                        .textSelection(.enabled)
                }
                if !review.paths.isEmpty {
                    List(review.paths, id: \.self) { path in
                        Label(path, systemImage: "doc")
                    }
                    .frame(minHeight: 80)
                }
                if !review.diff.isEmpty {
                    ScrollView {
                        Text(review.diff)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(minHeight: 160)
                }
            case .plan(let review):
                Label("Review Plan", systemImage: "list.clipboard")
                    .font(.title3)
                if !review.summary.isEmpty {
                    Text(review.summary)
                        .textSelection(.enabled)
                }
                if !review.originalRequest.isEmpty {
                    Text(review.originalRequest)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                if review.steps.isEmpty {
                    ContentUnavailableView("No Steps", systemImage: "list.clipboard")
                        .frame(minHeight: 180)
                } else {
                    List(review.steps, id: \.self) { step in
                        Label(step, systemImage: "checkmark.circle")
                    }
                    .frame(minHeight: 180)
                }
            }

            HStack {
                Spacer()
                Button("Deny") {
                    app.resolvePendingReview(allowed: false)
                }
                .keyboardShortcut(.cancelAction)
                Button("Approve") {
                    app.resolvePendingReview(allowed: true)
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 520, minHeight: 340)
    }
}

private struct StatusBadge: View {
    let state: ConnectionState

    var body: some View {
        Label(state.title, systemImage: symbol)
            .foregroundStyle(color)
            .labelStyle(.titleAndIcon)
    }

    private var symbol: String {
        switch state {
        case .stopped: "circle"
        case .starting: "arrow.clockwise"
        case .connected: "checkmark.circle.fill"
        case .failed: "xmark.octagon.fill"
        }
    }

    private var color: Color {
        switch state {
        case .stopped: .secondary
        case .starting: .orange
        case .connected: .green
        case .failed: .red
        }
    }
}
