import SwiftUI

struct DiffReviewView: View {
    @Environment(AppModel.self) private var app
    @State private var selectedEditID: DomainRecord.ID?
    @State private var previewText: String?

    private var records: [DomainRecord] {
        app.domainRecords[.review] ?? []
    }

    private var selectedEdit: DomainRecord? {
        records.first { $0.id == selectedEditID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                Group {
                    if records.isEmpty {
                        ContentUnavailableView(
                            "No Pending Edits",
                            systemImage: "doc.text.magnifyingglass",
                            description: Text("Click Refresh after the model stages edits.")
                        )
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        Table(records, selection: $selectedEditID) {
                            TableColumn("Edit") { record in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(record.title)
                                    Text(record.subtitle.isEmpty ? record.id : record.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            TableColumn("ID", value: \.id)
                        }
                    }
                }
                .onAppear {
                    if records.isEmpty {
                        Task { await refresh() }
                    }
                }
                .onChange(of: selectedEditID) { _, _ in
                    previewText = nil
                }
                .onChange(of: records) { _, value in
                    guard let selectedEditID else { return }
                    if !value.contains(where: { $0.id == selectedEditID }) {
                        self.selectedEditID = nil
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    HStack {
                        Button {
                            Task { await refresh() }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        Button {
                            Task { await preview() }
                        } label: {
                            Label("Preview", systemImage: "doc.text.magnifyingglass")
                        }
                        .disabled(selectedEdit == nil)
                        Spacer()
                    }
                    .padding(8)
                    .background(.bar)
                }
            }
            .frame(minWidth: 280, idealWidth: 340)

            VStack(alignment: .leading, spacing: 10) {
                if selectedEdit == nil {
                    ContentUnavailableView(
                        "No Pending Edit",
                        systemImage: "doc.text.magnifyingglass",
                        description: Text("Pending edits appear here after tools stage changes.")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    Text(selectedEdit?.title ?? "Pending Edit")
                        .font(.headline)
                    ScrollView {
                        Text(previewText ?? selectedEdit?.detail ?? "")
                            .font(.system(.body, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                    }
                }
                HStack {
                    Button {
                        Task { await accept() }
                    } label: {
                        Label("Accept", systemImage: "checkmark.circle")
                    }
                    .disabled(selectedEdit == nil || app.isBusy)
                    Button {
                        Task { await reject() }
                    } label: {
                        Label("Reject", systemImage: "xmark.circle")
                    }
                    .disabled(selectedEdit == nil || app.isBusy)
                }
            }
            .padding()
            .frame(minWidth: 340)
        }
    }

    private func refresh() async {
        await app.loadDomain(
            area: .review,
            action: BackendAction(area: .review, title: "Pending Edits", method: "diff.list")
        )
    }

    private func preview() async {
        guard let editID = selectedEdit?.id else { return }
        if let result = await app.callBackend(
            method: "diff.preview",
            params: ["editId": .string(editID)],
            title: "Preview edit"
        ) {
            previewText = result.prettyPrinted
        }
    }

    private func accept() async {
        guard let editID = selectedEdit?.id else { return }
        _ = await app.callBackend(
            method: "diff.accept",
            params: ["editId": .string(editID)],
            title: "Accept edit"
        )
        previewText = nil
        await refresh()
    }

    private func reject() async {
        guard let editID = selectedEdit?.id else { return }
        _ = await app.callBackend(
            method: "diff.reject",
            params: ["editId": .string(editID)],
            title: "Reject edit"
        )
        previewText = nil
        await refresh()
    }
}
