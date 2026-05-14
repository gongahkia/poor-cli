use serde::ser::SerializeStruct;
use serde::Serialize;
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("Keychain error: {0}")]
    Keychain(String),
    #[error("Network error: {0}")]
    Network(String),
    #[error("Provider error: {0}")]
    Provider(String),
    #[error("Parse error: {0}")]
    Parse(String),
    #[error("IO error: {0}")]
    Io(String),
}
impl AppError {
    pub fn code(&self) -> &'static str {
        match self {
            AppError::Keychain(_) => "KEYCHAIN_ERROR",
            AppError::Network(_) => "NETWORK_ERROR",
            AppError::Provider(_) => "PROVIDER_ERROR",
            AppError::Parse(_) => "PARSE_ERROR",
            AppError::Io(_) => "IO_ERROR",
        }
    }
}
impl Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where S: serde::Serializer {
        let mut state = serializer.serialize_struct("AppError", 2)?;
        state.serialize_field("code", self.code())?;
        state.serialize_field("message", &self.to_string())?;
        state.end()
    }
}
impl From<reqwest::Error> for AppError {
    fn from(e: reqwest::Error) -> Self { AppError::Network(e.to_string()) }
}
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self { AppError::Parse(e.to_string()) }
}
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self { AppError::Io(e.to_string()) }
}
