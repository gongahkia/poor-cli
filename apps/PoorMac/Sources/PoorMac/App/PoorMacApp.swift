import SwiftUI

@main
struct PoorMacApp: App {
    @State private var appModel = AppModel()

    var body: some Scene {
        WindowGroup("PoorMac") {
            RootView()
                .environment(appModel)
                .frame(minWidth: 980, minHeight: 640)
        }
        .commands {
            PoorMacCommands(app: appModel)
        }

        Settings {
            SettingsView()
                .environment(appModel)
                .frame(width: 560)
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
