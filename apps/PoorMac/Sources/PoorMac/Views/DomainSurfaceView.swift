import SwiftUI

struct DomainSurfaceView: View {
    @Environment(AppModel.self) private var app
    let area: BackendArea
    let primaryAction: BackendAction
    let actions: [BackendAction]
    @State private var selectedRecordID: DomainRecord.ID?

    private var records: [DomainRecord] {
        app.domainRecords[area] ?? []
    }

    private var selectedRecord: DomainRecord? {
        records.first { $0.id == selectedRecordID } ?? records.first
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                Group {
                    if records.isEmpty {
                        ContentUnavailableView(
                            "No \(area.title) Loaded",
                            systemImage: area.symbol,
                            description: Text("Click Refresh to load this backend domain.")
                        )
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        Table(records, selection: $selectedRecordID) {
                            TableColumn("Name") { record in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(record.title)
                                    if !record.subtitle.isEmpty {
                                        Text(record.subtitle)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            TableColumn("ID", value: \.id)
                        }
                    }
                }
                .onAppear {
                    if records.isEmpty {
                        Task { await app.loadDomain(area: area, action: primaryAction) }
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    HStack {
                        Button {
                            Task { await app.loadDomain(area: area, action: primaryAction) }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .disabled(app.isBusy)

                        Menu("Actions") {
                            ForEach(actions) { action in
                                Button(action.title) {
                                    Task { await app.loadDomain(area: area, action: action) }
                                }
                            }
                        }
                        Spacer()
                        Text("\(records.count) items")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.bar)
                }
            }
            .frame(minWidth: 360)

            VStack(alignment: .leading, spacing: 8) {
                if let selectedRecord {
                    Text(selectedRecord.title)
                        .font(.headline)
                    ScrollView {
                        Text(selectedRecord.detail)
                            .font(.system(.body, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                    }
                } else {
                    ContentUnavailableView(
                        "No Selection",
                        systemImage: area.symbol,
                        description: Text("Load \(area.title.lowercased()) data, then select a row.")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .padding()
            .frame(minWidth: 420)
        }
    }
}

extension BackendCatalog {
    static func primaryAction(for area: BackendArea) -> BackendAction {
        switch area {
        case .sessions:
            BackendCatalog.actions(for: .sessions).first { $0.method == "poor-cli/listSessions" }!
        case .context:
            BackendCatalog.actions(for: .context).first { $0.method == "context.snapshot" }!
        case .tools:
            BackendCatalog.actions(for: .tools).first { $0.method == "poor-cli/getTools" }!
        case .delivery:
            BackendCatalog.actions(for: .delivery).first { $0.method == "poor-cli/listCheckpoints" }!
        case .memory:
            BackendCatalog.actions(for: .memory).first { $0.method == "poor-cli/memoryList" }!
        case .services:
            BackendCatalog.actions(for: .services).first { $0.method == "poor-cli/getServiceStatus" }!
        case .workspace:
            BackendCatalog.actions(for: .workspace).first { $0.method == "poor-cli/getTrustStatus" }!
        default:
            BackendCatalog.actions(for: area).first ?? BackendAction(area: area, title: area.title, method: "getStartupState")
        }
    }
}
