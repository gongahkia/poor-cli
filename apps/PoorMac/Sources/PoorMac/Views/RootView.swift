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
                    }
                }
        }
    }

    private var selectionBinding: Binding<BackendArea?> {
        Binding(
            get: { app.selectedArea },
            set: { app.selectedArea = $0 ?? .dashboard }
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
        case .rpcConsole:
            RPCConsoleView()
        case .settings:
            SettingsView()
        default:
            FeatureSurfaceView(area: area)
        }
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
