import SwiftUI

struct ConversationView: View {
    @Environment(AppModel.self) private var app
    @AppStorage("PoorMac.developerMode") private var developerMode = false

    var body: some View {
        VStack(spacing: 0) {
            if developerMode {
                HSplitView {
                    ConversationTranscriptView()
                        .frame(minWidth: 360)
                    StreamEventsView()
                        .frame(minWidth: 220, idealWidth: 280)
                }
                .frame(minHeight: 320)
            } else {
                ConversationTranscriptView()
                    .frame(minHeight: 320)
            }
            Divider()
            ComposerPanel(
                chatText: chatBinding,
                execText: execBinding,
                showsExec: developerMode
            )
        }
    }

    private var chatBinding: Binding<String> {
        Binding(get: { app.chatDraft }, set: { app.chatDraft = $0 })
    }

    private var execBinding: Binding<String> {
        Binding(get: { app.execDraft }, set: { app.execDraft = $0 })
    }
}

private struct ConversationTranscriptView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        ScrollView {
            if app.chatTurns.isEmpty {
                ContentUnavailableView(
                    "No Conversation Yet",
                    systemImage: "bubble.left.and.bubble.right",
                    description: Text("Enter a prompt below, then press Send.")
                )
                .frame(maxWidth: .infinity, minHeight: 280)
            } else {
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
                        .padding(10)
                        .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 6))
                    }
                    if !app.streamEvents.isEmpty {
                        AgentActivityView(events: app.streamEvents)
                    }
                }
                .padding()
            }
        }
    }
}

private struct AgentActivityView: View {
    let events: [StreamEventLine]
    @State private var expanded = false

    private var visibleEvents: [StreamEventLine] {
        expanded ? Array(events.prefix(12)) : Array(events.prefix(3))
    }

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(visibleEvents) { event in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: event.symbol)
                            .foregroundStyle(.secondary)
                            .frame(width: 16)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(event.title)
                                .font(.callout)
                            if !event.detail.isEmpty {
                                Text(event.detail)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(expanded ? 6 : 2)
                            }
                        }
                    }
                }
            }
            .padding(.top, 8)
        } label: {
            Label("Agent Activity", systemImage: "sparkles")
                .font(.headline)
        }
        .padding(10)
        .background(.quaternary.opacity(0.28), in: RoundedRectangle(cornerRadius: 6))
    }
}

private struct ComposerPanel: View {
    @Environment(AppModel.self) private var app
    @Binding var chatText: String
    @Binding var execText: String
    let showsExec: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Message")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                PromptEditor(
                    text: $chatText,
                    placeholder: "Ask poor-cli to inspect, edit, explain, or run something...",
                    identifier: "PoorMac.Conversation.MessageEditor"
                )
                    .frame(minHeight: 72, idealHeight: 88, maxHeight: 110)
                HStack {
                    Button {
                        Task { await app.sendChat() }
                    } label: {
                        Label("Send", systemImage: "paperplane.fill")
                    }
                    .keyboardShortcut(.return, modifiers: [.command])
                    .accessibilityIdentifier("PoorMac.Conversation.Send")
                    .disabled(app.isBusy || chatText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Button {
                        Task { await app.cancelActiveRequest() }
                    } label: {
                        Label("Cancel", systemImage: "xmark.circle")
                    }
                    .accessibilityIdentifier("PoorMac.Conversation.Cancel")
                    .disabled(app.activeRequestID == nil)
                    Spacer()
                }
            }
            if showsExec {
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Text("Headless Exec")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    PromptEditor(
                        text: $execText,
                        placeholder: "Run a one-shot backend request...",
                        identifier: "PoorMac.Conversation.ExecEditor"
                    )
                        .frame(minHeight: 48, idealHeight: 58, maxHeight: 80)
                    Button {
                        Task { await app.runExec() }
                    } label: {
                        Label("Run Exec", systemImage: "play.rectangle")
                    }
                    .accessibilityIdentifier("PoorMac.Conversation.RunExec")
                    .disabled(app.isBusy || execText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .padding(12)
        .background(.background)
    }
}

private struct PromptEditor: View {
    @Binding var text: String
    let placeholder: String
    let identifier: String

    var body: some View {
        ZStack(alignment: .topLeading) {
            TextEditor(text: $text)
                .font(.body)
                .scrollContentBackground(.hidden)
                .padding(6)
            if text.isEmpty {
                Text(placeholder)
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 14)
                    .allowsHitTesting(false)
            }
        }
        .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 6))
        .overlay {
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.secondary.opacity(0.22))
        }
        .accessibilityIdentifier(identifier)
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
            if app.streamEvents.isEmpty {
                ContentUnavailableView(
                    "No Activity",
                    systemImage: "waveform.path.ecg",
                    description: Text("Streaming events appear during a backend request.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
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
}
