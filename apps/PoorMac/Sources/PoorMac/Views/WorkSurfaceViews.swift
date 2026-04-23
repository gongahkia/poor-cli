import SwiftUI

struct TaskSurfaceView: View {
    var body: some View {
        NativeActionSurface(
            area: .tasks,
            sections: [
                ActionSection(title: "Queue", actions: BackendCatalog.actions(for: .tasks)),
                ActionSection(title: "Agents", actions: BackendCatalog.actions(for: .tasks) + BackendCatalog.actions(for: .automation).prefix(1)),
            ]
        )
    }
}

struct AutomationSurfaceView: View {
    var body: some View {
        NativeActionSurface(
            area: .automation,
            sections: [
                ActionSection(title: "Rules", actions: BackendCatalog.actions(for: .automation)),
                ActionSection(title: "Run Control", actions: BackendCatalog.actions(for: .automation).filter { $0.method.contains("Run") || $0.method.contains("run") }),
            ]
        )
    }
}

struct DiagnosticsSurfaceView: View {
    var body: some View {
        NativeActionSurface(
            area: .diagnostics,
            sections: [
                ActionSection(title: "Health", actions: BackendCatalog.actions(for: .diagnostics)),
                ActionSection(title: "Workspace Safety", actions: BackendCatalog.actions(for: .workspace)),
            ]
        )
    }
}

struct CostSurfaceView: View {
    var body: some View {
        NativeActionSurface(
            area: .cost,
            sections: [
                ActionSection(title: "Spend", actions: BackendCatalog.actions(for: .cost)),
                ActionSection(title: "Context Budget", actions: BackendCatalog.actions(for: .context).filter { $0.method.contains("Context") || $0.method.contains("context") }),
            ]
        )
    }
}

struct ReviewSurfaceView: View {
    var body: some View {
        NativeActionSurface(
            area: .review,
            sections: [
                ActionSection(title: "Diff Review", actions: BackendCatalog.actions(for: .review)),
                ActionSection(title: "Checkpoints", actions: BackendCatalog.actions(for: .delivery).filter { $0.method.contains("Checkpoint") || $0.method.contains("checkpoint") }),
            ]
        )
    }
}

struct ActionSection: Identifiable {
    let id = UUID()
    let title: String
    let actions: [BackendAction]
}

struct NativeActionSurface: View {
    let area: BackendArea
    let sections: [ActionSection]

    var body: some View {
        VSplitView {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    ForEach(sections) { section in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(section.title)
                                .font(.headline)
                            if section.actions.isEmpty {
                                ContentUnavailableView(
                                    "No Actions",
                                    systemImage: area.symbol,
                                    description: Text("No backend actions are registered for this group.")
                                )
                                .frame(maxWidth: .infinity, minHeight: 120)
                            } else {
                                ActionGrid(actions: Array(section.actions))
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            ResultAndLogView()
                .frame(minHeight: 280)
        }
    }
}

struct ActionGrid: View {
    @Environment(AppModel.self) private var app
    let actions: [BackendAction]

    private let columns = [
        GridItem(.adaptive(minimum: 190), spacing: 12, alignment: .topLeading),
    ]

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
            ForEach(actions) { action in
                Button {
                    Task { await app.runAction(action) }
                } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(action.title)
                            .font(.callout)
                        Text(action.method)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .padding(.vertical, 4)
                    .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(app.isBusy)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
