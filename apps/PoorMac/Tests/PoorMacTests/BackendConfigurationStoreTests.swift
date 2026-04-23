import Foundation
@testable import PoorMac
import XCTest

final class BackendConfigurationStoreTests: XCTestCase {
    func testSavesAndLoadsNonSecretSettings() throws {
        let defaults = try makeDefaults()
        let base = BackendConfiguration(
            repoRoot: "/base/repo",
            pythonExecutable: "/usr/bin/env",
            provider: "",
            model: "",
            apiKey: "",
            permissionMode: "default",
            sandboxPreset: "workspace-write",
            validateAPIKey: false
        )
        let saved = BackendConfiguration(
            repoRoot: "/repo",
            pythonExecutable: "/python",
            provider: "openai",
            model: "gpt-test",
            apiKey: "secret",
            permissionMode: "prompt",
            sandboxPreset: "full-access",
            validateAPIKey: true
        )

        BackendConfigurationStore.save(saved, defaults: defaults)
        let loaded = BackendConfigurationStore.load(defaults: defaults, base: base)

        XCTAssertEqual(loaded.repoRoot, saved.repoRoot)
        XCTAssertEqual(loaded.pythonExecutable, saved.pythonExecutable)
        XCTAssertEqual(loaded.provider, saved.provider)
        XCTAssertEqual(loaded.model, saved.model)
        XCTAssertEqual(loaded.permissionMode, saved.permissionMode)
        XCTAssertEqual(loaded.sandboxPreset, saved.sandboxPreset)
        XCTAssertTrue(loaded.validateAPIKey)
        XCTAssertEqual(loaded.apiKey, "")
    }

    func testFallsBackToDetectedBaseWhenDefaultsAreEmpty() throws {
        let defaults = try makeDefaults()
        let base = BackendConfiguration(
            repoRoot: "/fallback/repo",
            pythonExecutable: "/fallback/python",
            provider: "fallback-provider",
            model: "fallback-model",
            apiKey: "session-only",
            permissionMode: "default",
            sandboxPreset: "workspace-write",
            validateAPIKey: false
        )

        let loaded = BackendConfigurationStore.load(defaults: defaults, base: base)

        XCTAssertEqual(loaded, base)
    }

    private func makeDefaults() throws -> UserDefaults {
        let suiteName = "PoorMacTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }
}
