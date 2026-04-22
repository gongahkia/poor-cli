import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        NavigationSplitView {
            List(BackendArea.allCases, selection: selectionBinding) { area in
                Label(area.title, systemImage: area.symbol)
                    .tag(area)
            }
            .navigationTitle("PoorMac")
            .navigationSplitViewColumnWidth(min: 220, ideal: 250, max: 320)
        } detail: {
            DetailRouter(area: app.selectedArea)
                .navigationTitle(app.selectedArea.title)
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
                        .disabled(app.isBusy)
                        Button {
                            Task { await app.stopBackend() }
                        } label: {
                            Label("Stop Backend", systemImage: "stop.fill")
                        }
                        Button {
                            Task { await app.cancelActiveRequest() }
                        } label: {
                            Label("Cancel Request", systemImage: "xmark.circle")
                        }
                        .disabled(app.activeRequestID == nil)
                    }
                }
                .sheet(item: reviewSheetBinding) { sheet in
                    ReviewSheetView(sheet: sheet)
                        .environment(app)
                }
        }
    }

    private var selectionBinding: Binding<BackendArea?> {
        Binding(
            get: { app.selectedArea },
            set: { app.selectedArea = $0 ?? .dashboard }
        )
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
            ReviewSurfaceView()
        case .rpcConsole:
            RPCConsoleView()
        case .settings:
            SettingsView()
        default:
            FeatureSurfaceView(area: area)
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
                List(review.steps, id: \.self) { step in
                    Label(step, systemImage: "checkmark.circle")
                }
                .frame(minHeight: 180)
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
