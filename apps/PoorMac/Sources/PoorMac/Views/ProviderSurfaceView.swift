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
            VStack(alignment: .leading, spacing: 0) {
                Group {
                    if providers.isEmpty {
                        ContentUnavailableView(
                            "No Providers Loaded",
                            systemImage: "cpu",
                            description: Text("Click Refresh to load provider status from the backend.")
                        )
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
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
                        .onChange(of: selectedProviderID) { _, value in
                            if let value {
                                app.configuration.provider = value
                            }
                        }
                    }
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
                .onChange(of: providers) { _, value in
                    guard let selectedProviderID else { return }
                    if !value.contains(where: { $0.id == selectedProviderID }) {
                        self.selectedProviderID = nil
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
                Section("Provider Setup") {
                    TextField("Provider", text: providerBinding)
                    TextField("Model", text: modelBinding)
                    SecureField("API key", text: apiKeyBinding)
                    HStack {
                        Button("Test") {
                            Task { await app.testProviderAPIKey() }
                        }
                        .disabled(app.configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        Button("Save") {
                            Task { await app.setProviderAPIKey() }
                        }
                        .disabled(app.configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || app.configuration.apiKey.isEmpty)
                        Button("Switch") {
                            Task { await app.switchProviderFromSettings() }
                        }
                        .disabled(app.configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }

                Section("Provider Operations") {
                    ActionGrid(actions: actions)
                }

                Section("Selected Provider Detail") {
                    if let detail = selectedProviderDetail {
                        ScrollView {
                            Text(detail)
                                .font(.system(.body, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(minHeight: 180)
                    } else {
                        ContentUnavailableView(
                            "No Provider Selected",
                            systemImage: "cpu",
                            description: Text("Refresh providers and select one to inspect readiness.")
                        )
                        .frame(minHeight: 180)
                    }
                }
            }
            .formStyle(.grouped)
            .frame(minWidth: 520)
        }
    }

    private var selectedProviderDetail: String? {
        providers.first { $0.id == selectedProviderID }?.detail
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
