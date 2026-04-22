import SwiftUI

struct RPCConsoleView: View {
    @Environment(AppModel.self) private var app
    @State private var selectedMethod: String?
    @State private var filter = ""

    private var methods: [String] {
        let query = filter.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return app.discoveredMethods }
        return app.discoveredMethods.filter { $0.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "magnifyingglass")
                    TextField("Filter methods", text: $filter)
                        .textFieldStyle(.plain)
                    Button {
                        app.refreshRegistry()
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .labelStyle(.iconOnly)
                }
                .padding(8)

                Table(methods.map(MethodRow.init), selection: $selectedMethod) {
                    TableColumn("Method", value: \.id)
                }
                .onChange(of: selectedMethod) { _, value in
                    if let value {
                        app.rpcMethod = value
                    }
                }
            }
            .frame(minWidth: 320, idealWidth: 380)

            VStack(alignment: .leading, spacing: 10) {
                Form {
                    Section("Request") {
                        TextField("Method", text: methodBinding)
                        TextEditor(text: paramsBinding)
                            .font(.system(.body, design: .monospaced))
                            .frame(minHeight: 160)
                            .overlay {
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Color.secondary.opacity(0.25))
                            }
                        Button {
                            Task { await app.runRPCConsole() }
                        } label: {
                            Label("Send RPC", systemImage: "paperplane")
                        }
                        .keyboardShortcut(.return, modifiers: [.command])
                        .disabled(app.isBusy)
                    }
                }
                .formStyle(.grouped)
                ResultAndLogView()
            }
            .frame(minWidth: 520)
        }
    }

    private var methodBinding: Binding<String> {
        Binding(get: { app.rpcMethod }, set: { app.rpcMethod = $0 })
    }

    private var paramsBinding: Binding<String> {
        Binding(get: { app.rpcParamsText }, set: { app.rpcParamsText = $0 })
    }
}

private struct MethodRow: Identifiable {
    let id: String
}
