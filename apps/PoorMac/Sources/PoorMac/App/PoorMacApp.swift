import SwiftUI

@main
struct PoorMacApp: App {
    @State private var appModel = AppModel()

    var body: some Scene {
        WindowGroup("PoorMac", id: "main") {
            RootView()
                .environment(appModel)
                .frame(minWidth: 1120, minHeight: 720)
        }
        .defaultSize(width: 1280, height: 800)
        .commands {
            PoorMacCommands(app: appModel)
        }

        Settings {
            SettingsView()
                .environment(appModel)
        }
    }
}

struct PoorMacCommands: Commands {
    let app: AppModel

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Button("Start Backend") {
                Task { await app.startBackend() }
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])

            Button("Stop Backend") {
                Task { await app.stopBackend() }
            }
            .keyboardShortcut(".", modifiers: [.command])
        }
    }
}
