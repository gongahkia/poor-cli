import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        Form {
            Section("Backend Process") {
                TextField("Repository root", text: repoRootBinding)
                TextField("Python executable", text: pythonBinding)
                Picker("Permission mode", selection: permissionBinding) {
                    ForEach(["default", "acceptEdits", "plan", "prompt", "auto-safe", "dontAsk", "bypassPermissions", "danger-full-access"], id: \.self) {
                        Text($0).tag($0)
                    }
                }
                Picker("Sandbox preset", selection: sandboxBinding) {
                    ForEach(["read-only", "review-only", "workspace-write", "full-access"], id: \.self) {
                        Text($0).tag($0)
                    }
                }
            }

            Section("Provider Override") {
                TextField("Provider", text: providerBinding)
                TextField("Model", text: modelBinding)
                SecureField("API key for this launch", text: apiKeyBinding)
                Toggle("Validate API key during initialize", isOn: validateBinding)
                HStack {
                    Button("Load Keychain") {
                        app.loadAPIKeyFromKeychain()
                    }
                    Button("Save Keychain") {
                        app.saveAPIKeyToKeychain()
                    }
                    .disabled(app.configuration.apiKey.isEmpty)
                    Button("Delete Keychain") {
                        app.deleteAPIKeyFromKeychain()
                    }
                }
                .disabled(app.configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if !app.keychainStatus.isEmpty {
                    Text(app.keychainStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                Button {
                    Task { await app.startBackend() }
                } label: {
                    Label("Apply and Restart Backend", systemImage: "arrow.clockwise")
                }
                .disabled(app.isBusy)
            }
        }
        .formStyle(.grouped)
        .padding()
    }

    private var repoRootBinding: Binding<String> {
        Binding(get: { app.configuration.repoRoot }, set: { app.configuration.repoRoot = $0 })
    }

    private var pythonBinding: Binding<String> {
        Binding(get: { app.configuration.pythonExecutable }, set: { app.configuration.pythonExecutable = $0 })
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

    private var permissionBinding: Binding<String> {
        Binding(get: { app.configuration.permissionMode }, set: { app.configuration.permissionMode = $0 })
    }

    private var sandboxBinding: Binding<String> {
        Binding(get: { app.configuration.sandboxPreset }, set: { app.configuration.sandboxPreset = $0 })
    }

    private var validateBinding: Binding<Bool> {
        Binding(get: { app.configuration.validateAPIKey }, set: { app.configuration.validateAPIKey = $0 })
    }
}
