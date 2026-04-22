import Foundation
import Security

enum KeychainStoreError: LocalizedError {
    case missingProvider
    case unexpectedStatus(OSStatus)

    var errorDescription: String? {
        switch self {
        case .missingProvider:
            "Set a provider before using Keychain."
        case .unexpectedStatus(let status):
            "Keychain operation failed with status \(status)."
        }
    }
}

enum KeychainStore {
    private static let service = "dev.poor-cli.PoorMac"

    static func readAPIKey(provider: String) throws -> String? {
        let account = try accountName(provider)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw KeychainStoreError.unexpectedStatus(status)
        }
        guard let data = result as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    static func saveAPIKey(_ apiKey: String, provider: String) throws {
        let account = try accountName(provider)
        let data = Data(apiKey.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attributes: [String: Any] = [
            kSecValueData as String: data,
        ]
        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if updateStatus == errSecSuccess {
            return
        }
        if updateStatus != errSecItemNotFound {
            throw KeychainStoreError.unexpectedStatus(updateStatus)
        }
        var addQuery = query
        addQuery[kSecValueData as String] = data
        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainStoreError.unexpectedStatus(addStatus)
        }
    }

    static func deleteAPIKey(provider: String) throws {
        let account = try accountName(provider)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        if status == errSecSuccess || status == errSecItemNotFound {
            return
        }
        throw KeychainStoreError.unexpectedStatus(status)
    }

    private static func accountName(_ provider: String) throws -> String {
        let trimmed = provider.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw KeychainStoreError.missingProvider
        }
        return trimmed
    }
}
