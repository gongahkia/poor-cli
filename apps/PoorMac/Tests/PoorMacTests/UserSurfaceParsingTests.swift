import Foundation
@testable import PoorMac
import XCTest

final class UserSurfaceParsingTests: XCTestCase {
    func testSessionRowsParseCommonBackendShape() {
        let value = JSONValue.object([
            "sessions": .array([
                .object([
                    "sessionId": .string("s1"),
                    "startedAt": .string("2026-04-23"),
                    "model": .string("gpt-test"),
                    "messageCount": .number(4),
                ]),
            ]),
        ])

        let rows = SessionListRow.rows(from: value)

        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows[0].id, "s1")
        XCTAssertEqual(rows[0].model, "gpt-test")
        XCTAssertEqual(rows[0].messageCount, "4")
    }
}
