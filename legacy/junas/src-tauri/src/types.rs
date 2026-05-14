use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String, // "user" | "assistant" | "system"
    pub content: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatSettings {
    pub temperature: Option<f64>,
    pub max_tokens: Option<u32>,
    pub top_p: Option<f64>,
    pub system_prompt: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderResponse {
    pub content: String,
    pub model: String,
    pub usage: Option<UsageInfo>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageInfo {
    pub prompt_tokens: Option<u32>,
    pub completion_tokens: Option<u32>,
    pub total_tokens: Option<u32>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamChunk {
    pub delta: String,
    pub done: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub title: String,
    pub url: String,
    pub snippet: String,
}
