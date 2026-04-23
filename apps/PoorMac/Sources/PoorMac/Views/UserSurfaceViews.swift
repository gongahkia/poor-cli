import SwiftUI

struct SessionsView: View {
    @Environment(AppModel.self) private var app
    @State private var rows: [SessionListRow] = []
    @State private var selectedID: SessionListRow.ID?
    @State private var query = ""

    private var filteredRows: [SessionListRow] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return rows }
        return rows.filter {
            $0.title.lowercased().contains(needle)
                || $0.subtitle.lowercased().contains(needle)
                || $0.id.lowercased().contains(needle)
        }
    }

    private var selectedRow: SessionListRow? {
        rows.first { $0.id == selectedID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                Table(filteredRows, selection: $selectedID) {
                    TableColumn("Session") { row in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.title)
                                .lineLimit(1)
                            if !row.subtitle.isEmpty {
                                Text(row.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }
                    TableColumn("Messages") { row in
                        Text(row.messageCount)
                            .foregroundStyle(.secondary)
                    }
                    TableColumn("Model", value: \.model)
                }
                .overlay {
                    if rows.isEmpty {
                        ContentUnavailableView(
                            "No Sessions",
                            systemImage: "rectangle.stack",
                            description: Text("Past conversations appear here after they are saved.")
                        )
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    HStack {
                        Button {
                            Task { await refresh() }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .disabled(app.isBusy)
                        Spacer()
                        Text("\(filteredRows.count) sessions")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.bar)
                }
            }
            .frame(minWidth: 360)

            SessionDetailView(row: selectedRow)
                .frame(minWidth: 320)
        }
        .searchable(text: $query, placement: .toolbar, prompt: "Search sessions")
        .task {
            if rows.isEmpty {
                await refresh()
            }
        }
    }

    private func refresh() async {
        guard let result = await app.callBackend(
            method: "poor-cli/listSessions",
            params: ["limit": .number(50)],
            title: "List Sessions"
        ) else {
            return
        }
        rows = SessionListRow.rows(from: result)
        if let selectedID, !rows.contains(where: { $0.id == selectedID }) {
            self.selectedID = nil
        }
    }
}

private struct SessionDetailView: View {
    let row: SessionListRow?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let row {
                Label(row.title, systemImage: "bubble.left.and.bubble.right")
                    .font(.title3)
                LabeledContent("Session ID", value: row.id)
                LabeledContent("Updated", value: row.updatedAt)
                LabeledContent("Model", value: row.model)
                LabeledContent("Messages", value: row.messageCount)
                Spacer()
            } else {
                ContentUnavailableView(
                    "No Session Selected",
                    systemImage: "rectangle.stack",
                    description: Text("Select a session to inspect it.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding()
    }
}

struct UsageView: View {
    @Environment(AppModel.self) private var app
    @State private var costSummary: JSONValue?
    @State private var costHistory: JSONValue?
    @State private var contextPressure: JSONValue?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Usage")
                    .font(.largeTitle.bold())
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], alignment: .leading, spacing: 12) {
                    UsageMetricCard(
                        title: "Session Spend",
                        value: costSummary?.displayValue(for: ["sessionCostUsd", "session_cost_usd", "costUsd", "totalCostUsd"]) ?? "Unavailable",
                        detail: app.configuration.model.isEmpty ? app.configuration.provider : app.configuration.model,
                        symbol: "dollarsign.circle"
                    )
                    UsageMetricCard(
                        title: "Tokens",
                        value: costSummary?.displayValue(for: ["totalTokens", "total_tokens", "tokens"]) ?? "Unavailable",
                        detail: "Current session",
                        symbol: "number"
                    )
                    UsageMetricCard(
                        title: "Context",
                        value: contextPressure?.displayValue(for: ["status", "pressure", "level"]) ?? "Unavailable",
                        detail: contextPressure?.displayValue(for: ["budget", "contextBudget", "tokens"]) ?? "Budget not loaded",
                        symbol: "text.magnifyingglass"
                    )
                    UsageMetricCard(
                        title: "Recent Records",
                        value: costHistory?.collectionCountText ?? "Unavailable",
                        detail: "Cost history",
                        symbol: "clock"
                    )
                }
                HStack {
                    Button {
                        Task { await refresh() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .disabled(app.isBusy)
                    Spacer()
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .task {
            if costSummary == nil {
                await refresh()
            }
        }
    }

    private func refresh() async {
        costSummary = await app.callBackend(method: "poor-cli/costSummary", title: "Cost Summary")
        costHistory = await app.callBackend(method: "cost.history", title: "Cost History")
        contextPressure = await app.callBackend(method: "poor-cli/getContextPressure", title: "Context Pressure")
    }
}

private struct UsageMetricCard: View {
    let title: String
    let value: String
    let detail: String
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: symbol)
                .font(.headline)
            Text(value.isEmpty ? "Unavailable" : value)
                .font(.title2.bold())
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            if !detail.isEmpty {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, minHeight: 118, alignment: .leading)
        .background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct SessionListRow: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let updatedAt: String
    let model: String
    let messageCount: String

    static func rows(from value: JSONValue) -> [SessionListRow] {
        let sessions = value.objectValue?["sessions"]?.arrayValue ?? value.arrayValue ?? []
        return sessions.enumerated().map { index, item in
            let object = item.objectValue ?? [:]
            let id = object.firstString(["sessionId", "session_id", "id"]) ?? "session-\(index + 1)"
            let title = object.firstString(["label", "title", "name"]) ?? id
            let updated = object.firstString(["updatedAt", "startedAt", "endedAt", "savedAt", "created_at"]) ?? ""
            let model = object.firstString(["model", "provider"]) ?? ""
            let count = object.firstString(["messageCount", "message_count", "messages"]) ?? ""
            let subtitle = [updated, model].filter { !$0.isEmpty }.joined(separator: " | ")
            return SessionListRow(
                id: id,
                title: title,
                subtitle: subtitle,
                updatedAt: updated,
                model: model,
                messageCount: count
            )
        }
    }
}

private extension JSONValue {
    func displayValue(for keys: [String]) -> String? {
        guard let object = objectValue else { return nil }
        return object.firstString(keys)
    }

    var collectionCountText: String? {
        if let array = arrayValue {
            return "\(array.count)"
        }
        guard let object = objectValue else { return nil }
        for value in object.values {
            if let array = value.arrayValue {
                return "\(array.count)"
            }
        }
        return nil
    }
}

private extension Dictionary where Key == String, Value == JSONValue {
    func firstString(_ keys: [String]) -> String? {
        for key in keys {
            guard let value = self[key] else { continue }
            if let string = value.stringValue, !string.isEmpty {
                return string
            }
            if let number = value.intValue {
                return String(number)
            }
            if case .number(let double) = value {
                return String(format: "%.4f", double)
            }
            if case .bool(let bool) = value {
                return bool ? "Yes" : "No"
            }
        }
        return nil
    }
}
