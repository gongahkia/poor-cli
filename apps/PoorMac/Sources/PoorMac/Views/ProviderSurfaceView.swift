import SwiftUI

struct ProviderSurfaceView: View {
    @Environment(AppModel.self) private var app
    @State private var selectedProviderID: DomainRecord.ID?

    private let actions: [BackendAction] = BackendCatalog.actions(for: .providers)
    private var providers: [DomainRecord] {
        app.domainRecords[.providers] ?? []
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                Table(providers, selection: $selectedProviderID) {
                    TableColumn("Provider") { provider in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(provider.title)
                            if !provider.subtitle.isEmpty {
                                Text(provider.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    TableColumn("ID", value: \.id)
                }
                .onAppear {
                    if providers.isEmpty {
                        Task {
                            await app.loadDomain(
                                area: .providers,
                                action: BackendAction(area: .providers, title: "List Providers", method: "poor-cli/listProviders")
                            )
                        }
                    }
                }
                .onChange(of: selectedProviderID) { _, value in
                    if let value {
                        app.configuration.provider = value
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    HStack {
                        Button {
                            Task {
                                await app.loadDomain(
                                    area: .providers,
                                    action: BackendAction(area: .providers, title: "List Providers", method: "poor-cli/listProviders")
                                )
                            }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        Spacer()
                        Text("\(providers.count) providers")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.bar)
                }
            }
            .frame(minWidth: 360)

            Form {
                Section("Active Launch Overrides") {
                    LabeledContent("Provider", value: app.configuration.provider.isEmpty ? "Default" : app.configuration.provider)
                    LabeledContent("Model", value: app.configuration.model.isEmpty ? "Default" : app.configuration.model)
                    LabeledContent("API key", value: app.configuration.apiKey.isEmpty ? "Environment or backend store" : "Session override")
                    TextField("Provider", text: providerBinding)
                    TextField("Model", text: modelBinding)
                    SecureField("API key", text: apiKeyBinding)
                    HStack {
                        Button("Test") {
                            Task { await app.testProviderAPIKey() }
                        }
                        Button("Save") {
                            Task { await app.setProviderAPIKey() }
                        }
                        .disabled(app.configuration.apiKey.isEmpty)
                        Button("Switch") {
                            Task { await app.switchProviderFromSettings() }
                        }
                    }
                }

                Section("Provider Operations") {
                    ActionGrid(actions: actions)
                }

                Section("Selected Provider Detail") {
                    ScrollView {
                        Text(selectedProviderDetail)
                            .font(.system(.body, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(minHeight: 180)
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 520)
        }
    }

    private var selectedProviderDetail: String {
        providers.first { $0.id == selectedProviderID }?.detail ?? app.lastResult.prettyPrinted
    }

    private var providerBinding: Binding<String> {
        Binding(get: { app.configuration.provider }, set: { app.configuration.provider = $0 })
    }

    private var modelBinding: Binding<String> {
        Binding(get: { app.configuration.model }, set: { app.configuration.model = $0 })
    }

    private var apiKeyBinding: Binding<String> {
        Binding(get: { app.configuration.apiKey }, set: { app.configuration.apiKey = $0 })
    }
}
