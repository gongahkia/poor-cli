import SwiftUI

struct DashboardView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section("Backend") {
                    LabeledContent("State", value: app.connectionState.title)
                    LabeledContent("Repo", value: app.statusDetail)
                    LabeledContent("Discovered RPC methods", value: "\(app.discoveredMethods.count)")
                }
                Section("Quick Actions") {
                    ActionGrid(actions: BackendCatalog.actions(for: .dashboard))
                }
            }
            .formStyle(.grouped)
            Divider()
            ResultAndLogView()
        }
    }
}

struct ResultAndLogView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 8) {
                Text("Result")
                    .font(.headline)
                if app.lastResult.objectValue?.isEmpty == true {
                    ContentUnavailableView(
                        "No Result",
                        systemImage: "doc.text",
                        description: Text("Run a backend action to inspect its response.")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        Text(app.lastResult.prettyPrinted)
                            .font(.system(.body, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                    }
                }
            }
            .frame(minWidth: 360)

            VStack(alignment: .leading, spacing: 8) {
                Text("Recent Calls")
                    .font(.headline)
                if app.logs.isEmpty {
                    ContentUnavailableView(
                        "No Recent Calls",
                        systemImage: "clock",
                        description: Text("Backend call history appears here.")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(app.logs) { line in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(line.title)
                                .font(.callout)
                            Text(line.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            }
            .frame(minWidth: 300)
        }
        .padding()
    }
}
