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
            Group {
                if actions.isEmpty {
                    ContentUnavailableView(
                        "No Actions",
                        systemImage: area.symbol,
                        description: Text("No backend actions are registered for this screen.")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
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
                            run(selection: selection)
                        }
                    } primaryAction: { selection in
                        run(selection: selection)
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                HStack {
                    Button {
                        run(selection: selectedActionID.map { [$0] } ?? [])
                    } label: {
                        Label("Run Selected", systemImage: "play.fill")
                    }
                    .disabled(selectedActionID == nil || app.isBusy)

                    Spacer()
                    Text("\(actions.count) actions")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .background(.bar)
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
