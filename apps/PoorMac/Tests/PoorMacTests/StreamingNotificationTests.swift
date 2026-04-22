import Foundation
@testable import PoorMac
import XCTest

@MainActor
final class StreamingNotificationTests: XCTestCase {
    func testStreamChunkAppendsAssistantContent() async {
        let app = AppModel()
        let assistantID = UUID()
        app.chatTurns.append(ChatTurn(id: assistantID, role: "assistant", content: ""))

        _ = await app.handleStreamingNotification(
            JSONRPCNotificationEvent(method: "poor-cli/streamChunk", params: [
                "chunk": .string("hello"),
                "done": .bool(false),
            ]),
            assistantID: assistantID
        )

        XCTAssertEqual(app.chatTurns.first?.content, "hello")
    }

    func testToolChunkReturnsAckNotification() async throws {
        let app = AppModel()
        let outbound = await app.handleStreamingNotification(
            JSONRPCNotificationEvent(method: "tool.chunk", params: [
                "eventId": .string("evt-1"),
                "toolName": .string("bash"),
                "chunkIndex": .number(2),
                "chunk": .string("out"),
            ]),
            assistantID: UUID()
        )

        let notification = try XCTUnwrap(outbound)
        XCTAssertEqual(notification.method, "poor-cli/toolStreamAck")
        XCTAssertEqual(notification.params["eventId"], .string("evt-1"))
        XCTAssertEqual(notification.params["chunksProcessed"], .number(3))
    }

    func testPermissionReviewResolvesToResponse() async throws {
        let app = AppModel()
        let task = Task {
            await app.handleStreamingNotification(
                JSONRPCNotificationEvent(method: "poor-cli/permissionReq", params: [
                    "promptId": .string("perm-1"),
                    "toolName": .string("write_file"),
                    "operation": .string("write"),
                    "paths": .array([.string("README.md")]),
                ]),
                assistantID: UUID()
            )
        }

        while app.pendingReviewSheet == nil {
            try await Task.sleep(nanoseconds: 1_000_000)
        }
        app.resolvePendingReview(allowed: true)
        let outbound = await task.value
        let notification = try XCTUnwrap(outbound)
        XCTAssertEqual(notification.method, "poor-cli/permissionRes")
        XCTAssertEqual(notification.params["promptId"], .string("perm-1"))
        XCTAssertEqual(notification.params["allowed"], .bool(true))
    }
}
