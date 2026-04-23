@testable import PoorMac
import XCTest

final class BackendCatalogTests: XCTestCase {
    func testSidebarAreasAreUniqueAndExcludeSettings() {
        let ids = BackendArea.allCases.map(\.rawValue)

        XCTAssertEqual(Set(ids).count, ids.count)
        XCTAssertFalse(ids.contains("settings"))
    }

    func testPrimaryActionsResolveForDomainScreens() {
        let domainAreas: [BackendArea] = [
            .sessions,
            .context,
            .tools,
            .delivery,
            .memory,
            .services,
            .workspace,
        ]

        for area in domainAreas {
            let action = BackendCatalog.primaryAction(for: area)
            XCTAssertEqual(action.area, area)
            XCTAssertFalse(action.method.isEmpty)
        }
    }

    func testActionIdentifiersAreUniqueWithinEachArea() {
        for area in BackendArea.allCases {
            let ids = BackendCatalog.actions(for: area).map(\.id)
            XCTAssertEqual(Set(ids).count, ids.count, "\(area.rawValue) has duplicate action ids")
        }
    }
}
