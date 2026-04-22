import SwiftUI

struct ProviderSurfaceView: View {
    @Environment(AppModel.self) private var app

    private let actions: [BackendAction] = BackendCatalog.actions(for: .providers)

    var body: some View {
        VSplitView {
            Form {
                Section("Active Launch Overrides") {
                    LabeledContent("Provider", value: app.configuration.provider.isEmpty ? "Default" : app.configuration.provider)
                    LabeledContent("Model", value: app.configuration.model.isEmpty ? "Default" : app.configuration.model)
                    LabeledContent("API key", value: app.configuration.apiKey.isEmpty ? "Environment or backend store" : "Session override")
                    Button {
                        app.selectedArea = .settings
                    } label: {
                        Label("Open Settings", systemImage: "gearshape")
                    }
                }

                Section("Provider Operations") {
                    ActionGrid(actions: actions)
                }
            }
            .formStyle(.grouped)

            ResultAndLogView()
                .frame(minHeight: 280)
        }
    }
}
