import SwiftUI

struct ConversationView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(app.chatTurns) { turn in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(turn.role.capitalized)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(turn.content)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .padding()
            }
            Divider()
            VStack(alignment: .leading, spacing: 8) {
                TextEditor(text: chatBinding)
                    .font(.body)
                    .frame(minHeight: 88, maxHeight: 130)
                    .overlay {
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.25))
                    }
                HStack {
                    Button {
                        Task { await app.sendChat() }
                    } label: {
                        Label("Send", systemImage: "paperplane.fill")
                    }
                    .keyboardShortcut(.return, modifiers: [.command])
                    .disabled(app.isBusy)
                }
                Divider()
                TextEditor(text: execBinding)
                    .font(.body)
                    .frame(minHeight: 54, maxHeight: 90)
                    .overlay {
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.25))
                    }
                Button {
                    Task { await app.runExec() }
                } label: {
                    Label("Run Exec", systemImage: "play.rectangle")
                }
                .disabled(app.isBusy)
            }
            .padding()
        }
    }

    private var chatBinding: Binding<String> {
        Binding(get: { app.chatDraft }, set: { app.chatDraft = $0 })
    }

    private var execBinding: Binding<String> {
        Binding(get: { app.execDraft }, set: { app.execDraft = $0 })
    }
}
