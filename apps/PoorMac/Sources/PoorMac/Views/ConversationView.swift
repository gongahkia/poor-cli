import SwiftUI

struct ConversationView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        VSplitView {
            HSplitView {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(app.chatTurns) { turn in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(turn.role.capitalized)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(turn.content.isEmpty ? " " : turn.content)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                    .padding()
                }
                .frame(minWidth: 520)

                StreamEventsView()
                    .frame(minWidth: 260, idealWidth: 320)
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
                    Button {
                        Task { await app.cancelActiveRequest() }
                    } label: {
                        Label("Cancel", systemImage: "xmark.circle")
                    }
                    .disabled(app.activeRequestID == nil)
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

private struct StreamEventsView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Activity")
                .font(.headline)
                .padding(.horizontal)
                .padding(.top, 8)
            List(app.streamEvents) { event in
                VStack(alignment: .leading, spacing: 3) {
                    Label(event.title, systemImage: event.symbol)
                        .font(.callout)
                    if !event.detail.isEmpty {
                        Text(event.detail)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(3)
                    }
                }
            }
        }
    }
}
