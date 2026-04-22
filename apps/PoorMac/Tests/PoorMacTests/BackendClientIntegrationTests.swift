import Foundation
@testable import PoorMac
import XCTest

final class BackendClientIntegrationTests: XCTestCase {
    func testLaunchesBackendAndReadsStartupState() async throws {
        let configuration = BackendConfiguration.detected()
        guard FileManager.default.fileExists(atPath: "\(configuration.repoRoot)/pyproject.toml") else {
            throw XCTSkip("poor-cli repo root not available")
        }

        let client = JSONRPCStdioClient(configuration: configuration)
        do {
            let result = try await client.call(method: "getStartupState")
            XCTAssertNotNil(result.objectValue)
            await client.shutdownIfRunning()
        } catch {
            await client.shutdownIfRunning()
            throw error
        }
    }
}
