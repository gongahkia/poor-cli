import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        TabView {
            Form {
                Section("Backend Process") {
                    TextField("Repository root", text: repoRootBinding)
                        .accessibilityIdentifier("PoorMac.Settings.RepoRoot")
                    TextField("Python executable", text: pythonBinding)
                        .accessibilityIdentifier("PoorMac.Settings.PythonExecutable")
                    ValidationRow(
                        title: "Repository root",
                        isValid: repositoryExists,
                        detail: repositoryExists ? "Found" : "Path does not exist"
                    )
                    ValidationRow(
                        title: "Python executable",
                        isValid: pythonExecutableValid,
                        detail: pythonExecutableValid ? "Runnable" : "Executable not found"
                    )
                    Picker("Permission mode", selection: permissionBinding) {
                        ForEach(["default", "acceptEdits", "plan", "prompt", "auto-safe", "dontAsk", "bypassPermissions", "danger-full-access"], id: \.self) {
                            Text($0).tag($0)
                        }
                    }
                    .accessibilityIdentifier("PoorMac.Settings.PermissionMode")
                    Picker("Sandbox preset", selection: sandboxBinding) {
                        ForEach(["read-only", "review-only", "workspace-write", "full-access"], id: \.self) {
                            Text($0).tag($0)
                        }
                    }
                    .accessibilityIdentifier("PoorMac.Settings.SandboxPreset")
                }

                Section {
                    Button {
                        Task { await app.startBackend() }
                    } label: {
                        Label("Apply and Restart Backend", systemImage: "arrow.clockwise")
                    }
                    .accessibilityIdentifier("PoorMac.Settings.ApplyRestart")
                    .disabled(app.isBusy || !repositoryExists || !pythonExecutableValid)
                }
            }
            .formStyle(.grouped)
            .padding()
            .tabItem {
                Label("Backend", systemImage: "server.rack")
            }

            Form {
                Section("Provider Override") {
                    TextField("Provider", text: providerBinding)
                        .accessibilityIdentifier("PoorMac.Settings.Provider")
                    TextField("Model", text: modelBinding)
                        .accessibilityIdentifier("PoorMac.Settings.Model")
                    SecureField("API key for this launch", text: apiKeyBinding)
                        .accessibilityIdentifier("PoorMac.Settings.APIKey")
                    Toggle("Validate API key during initialize", isOn: validateBinding)
                        .accessibilityIdentifier("PoorMac.Settings.ValidateAPIKey")
                    HStack {
                        Button("Load Keychain") {
                            app.loadAPIKeyFromKeychain()
                        }
                        .accessibilityIdentifier("PoorMac.Settings.LoadKeychain")
                        Button("Save Keychain") {
                            app.saveAPIKeyToKeychain()
                        }
                        .accessibilityIdentifier("PoorMac.Settings.SaveKeychain")
                        .disabled(app.configuration.apiKey.isEmpty)
                        Button("Delete Keychain") {
                            app.deleteAPIKeyFromKeychain()
                        }
                        .accessibilityIdentifier("PoorMac.Settings.DeleteKeychain")
                    }
                    .disabled(app.configuration.provider.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    if !app.keychainStatus.isEmpty {
                        Text(app.keychainStatus)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .formStyle(.grouped)
            .padding()
            .tabItem {
                Label("Provider", systemImage: "cpu")
            }
        }
        .frame(width: 620, height: 420)
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

    private var repositoryExists: Bool {
        FileManager.default.fileExists(atPath: app.configuration.repoRoot)
    }

    private var pythonExecutableValid: Bool {
        app.configuration.pythonExecutable == "/usr/bin/env"
            || FileManager.default.isExecutableFile(atPath: app.configuration.pythonExecutable)
    }
}

private struct ValidationRow: View {
    let title: String
    let isValid: Bool
    let detail: String

    var body: some View {
        LabeledContent(title) {
            Label(detail, systemImage: isValid ? "checkmark.circle.fill" : "xmark.octagon.fill")
                .foregroundStyle(isValid ? .green : .red)
        }
    }
}
