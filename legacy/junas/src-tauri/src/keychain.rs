use crate::error::AppError;
use keyring::Entry;
const SERVICE: &str = "com.gongahkia.junas";
fn entry(provider: &str) -> Result<Entry, AppError> {
    Entry::new(SERVICE, provider)
        .map_err(|e| AppError::Keychain(format!("keyring init failed for {provider}: {e}")))
}
#[tauri::command]
pub fn get_api_key(provider: String) -> Result<String, AppError> {
    entry(&provider)?
        .get_password()
        .map_err(|e| AppError::Keychain(format!("key not found for {provider}: {e}")))
}
#[tauri::command]
pub fn set_api_key(provider: String, key: String) -> Result<(), AppError> {
    entry(&provider)?
        .set_password(&key)
        .map_err(|e| AppError::Keychain(format!("failed to store key for {provider}: {e}")))
}
#[tauri::command]
pub fn delete_api_key(provider: String) -> Result<(), AppError> {
    entry(&provider)?
        .delete_credential()
        .map_err(|e| AppError::Keychain(format!("failed to delete key for {provider}: {e}")))
}
