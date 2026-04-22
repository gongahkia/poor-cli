import Foundation
@testable import PoorMac
import XCTest

final class JSONRPCFramingTests: XCTestCase {
    func testFrameUsesContentLengthHeader() throws {
        let body = Data(#"{"jsonrpc":"2.0","id":1,"result":true}"#.utf8)
        let framed = JSONRPCFraming.frame(body)
        let delimiter = JSONRPCFraming.delimiter
        guard let delimiterRange = framed.range(of: delimiter) else {
            return XCTFail("missing delimiter")
        }
        let header = framed[..<delimiterRange.upperBound]
        XCTAssertEqual(try JSONRPCFraming.contentLength(from: Data(header)), body.count)
        XCTAssertEqual(framed[delimiterRange.upperBound...], body)
    }

    func testJSONValueRoundTripObject() throws {
        let raw = Data(#"{"text":"hello","count":2,"ok":true,"items":[null,"x"]}"#.utf8)
        let decoded = try JSONDecoder().decode(JSONValue.self, from: raw)
        let object = try XCTUnwrap(decoded.objectValue)
        XCTAssertEqual(object["text"]?.stringValue, "hello")
        XCTAssertEqual(object["items"]?.arrayValue?.count, 2)

        let encoded = try JSONEncoder().encode(decoded)
        let encodedObject = try JSONDecoder().decode(JSONValue.self, from: encoded).objectValue
        XCTAssertEqual(encodedObject?["ok"], .bool(true))
    }

    func testInvalidContentLengthThrows() {
        let header = Data("Content-Type: application/json\r\n\r\n".utf8)
        XCTAssertThrowsError(try JSONRPCFraming.contentLength(from: header))
    }
}
