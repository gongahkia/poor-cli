import SwiftUI

struct FeatureSurfaceView: View {
    @Environment(AppModel.self) private var app
    let area: BackendArea
    @State private var selectedActionID: BackendAction.ID?

    private var actions: [BackendAction] {
        BackendCatalog.actions(for: area)
    }

    var body: some View {
        VStack(spacing: 0) {
            FeatureActionList(
                area: area,
                actions: actions,
                selectedActionID: $selectedActionID,
                isBusy: app.isBusy,
                run: run(selection:)
            )
            .safeAreaInset(edge: .bottom) {
                FeatureActionBar(
                    actionCount: actions.count,
                    selectedActionID: selectedActionID,
                    isBusy: app.isBusy,
                    run: run(selection:)
                )
            }

            Divider()
            ResultAndLogView()
                .frame(minHeight: 260)
        }
    }

    private func run(selection: Set<BackendAction.ID>) {
        guard let id = selection.first,
              let action = actions.first(where: { $0.id == id })
        else { return }
        Task { await app.runAction(action) }
    }
}

private struct FeatureActionList: View {
    let area: BackendArea
    let actions: [BackendAction]
    @Binding var selectedActionID: BackendAction.ID?
    let isBusy: Bool
    let run: (Set<BackendAction.ID>) -> Void

    var body: some View {
        if actions.isEmpty {
            FeatureEmptyState(area: area)
        } else {
            FeatureActionTable(
                area: area,
                actions: actions,
                selectedActionID: $selectedActionID,
                isBusy: isBusy,
                run: run
            )
        }
    }
}

private struct FeatureEmptyState: View {
    let area: BackendArea

    var body: some View {
        ContentUnavailableView(
            "No Actions",
            systemImage: area.symbol,
            description: Text("No backend actions are registered for this screen.")
        )
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct FeatureActionTable: View {
    let area: BackendArea
    let actions: [BackendAction]
    @Binding var selectedActionID: BackendAction.ID?
    let isBusy: Bool
    let run: (Set<BackendAction.ID>) -> Void

    var body: some View {
        Table(actions, selection: $selectedActionID) {
            TableColumn("Action") { action in
                Label(action.title, systemImage: area.symbol)
            }
            TableColumn("RPC Method", value: \.method)
            TableColumn("Params") { action in
                Text(action.params.isEmpty ? "none" : JSONValue.object(action.params).prettyPrinted)
                    .font(.system(.caption, design: .monospaced))
                    .lineLimit(1)
            }
        }
        .contextMenu(forSelectionType: BackendAction.ID.self) { selection in
            Button("Run") {
                run(selection)
            }
            .disabled(isBusy || selection.isEmpty)
        } primaryAction: { selection in
            if !isBusy {
                run(selection)
            }
        }
    }
}

private struct FeatureActionBar: View {
    let actionCount: Int
    let selectedActionID: BackendAction.ID?
    let isBusy: Bool
    let run: (Set<BackendAction.ID>) -> Void

    var body: some View {
        HStack {
            Button {
                run(selectedActionID.map { [$0] } ?? [])
            } label: {
                Label("Run Selected", systemImage: "play.fill")
            }
            .disabled(selectedActionID == nil || isBusy)

            Spacer()
            Text("\(actionCount) actions")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(8)
        .background(.bar)
    }
}
