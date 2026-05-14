use crate::error::AppError;
use crate::types::SearchResult;
use futures_util::StreamExt;
use kuchiki::traits::*;

const MAX_FETCH_BODY_BYTES: usize = 2 * 1024 * 1024;
const TOOL_CONNECT_TIMEOUT_SECS: u64 = 10;
const TOOL_REQUEST_TIMEOUT_SECS: u64 = 20;
// task 26: fetch url, sanitize html, return markdown-ish text
#[tauri::command]
pub async fn fetch_url(url: String) -> Result<String, AppError> {
    let normalized_url = normalize_fetch_url(&url)?;
    let client = reqwest::Client::builder()
        .user_agent("Junas/0.1")
        .connect_timeout(std::time::Duration::from_secs(TOOL_CONNECT_TIMEOUT_SECS))
        .timeout(std::time::Duration::from_secs(TOOL_REQUEST_TIMEOUT_SECS))
        .build()
        .map_err(|e| AppError::Network(e.to_string()))?;
    let resp = client.get(&normalized_url).send().await?;
    if !resp.status().is_success() {
        return Err(AppError::Network(format!("HTTP {}", resp.status())));
    }

    if let Some(content_length) = resp.content_length() {
        if content_length > MAX_FETCH_BODY_BYTES as u64 {
            return Err(AppError::Network(format!(
                "Response too large ({} bytes). Limit is {} bytes.",
                content_length, MAX_FETCH_BODY_BYTES
            )));
        }
    }

    let mut body: Vec<u8> = Vec::new();
    let mut stream = resp.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(AppError::from)?;
        if body.len() + chunk.len() > MAX_FETCH_BODY_BYTES {
            return Err(AppError::Network(format!(
                "Response exceeded maximum size limit of {} bytes.",
                MAX_FETCH_BODY_BYTES
            )));
        }
        body.extend_from_slice(&chunk);
    }

    let text = String::from_utf8_lossy(&body).to_string();
    Ok(extract_text_from_html(&text))
}

fn normalize_fetch_url(url: &str) -> Result<String, AppError> {
    let trimmed = url.trim();
    if trimmed.is_empty() {
        return Err(AppError::Parse("URL is empty".to_string()));
    }

    let candidate = if trimmed.starts_with("http://") || trimmed.starts_with("https://") {
        trimmed.to_string()
    } else {
        format!("https://{}", trimmed)
    };

    let parsed = reqwest::Url::parse(&candidate)
        .map_err(|e| AppError::Parse(format!("Invalid URL: {}", e)))?;

    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(AppError::Parse(
            "Only http:// and https:// URLs are supported".to_string(),
        ));
    }

    if parsed.host_str().is_none() {
        return Err(AppError::Parse("URL must include a host".to_string()));
    }

    Ok(parsed.to_string())
}

fn extract_text_from_html(html: &str) -> String {
    let document = kuchiki::parse_html().one(html);

    for selector in ["script", "style", "noscript"] {
        if let Ok(nodes) = document.select(selector) {
            for node in nodes {
                node.as_node().detach();
            }
        }
    }

    normalize_whitespace(&document.text_contents())
}

fn normalize_whitespace(input: &str) -> String {
    input
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
// task 27: web search via serper.dev
#[tauri::command]
pub async fn web_search(query: String, api_key: String) -> Result<Vec<SearchResult>, AppError> {
    let client = reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(TOOL_CONNECT_TIMEOUT_SECS))
        .timeout(std::time::Duration::from_secs(TOOL_REQUEST_TIMEOUT_SECS))
        .build()
        .map_err(|e| AppError::Network(e.to_string()))?;
    let resp = client.post("https://google.serper.dev/search")
        .header("X-API-KEY", &api_key)
        .json(&serde_json::json!({"q": query}))
        .send().await?;
    if !resp.status().is_success() {
        return Err(AppError::Network(format!("Serper API {}", resp.status())));
    }
    let body: serde_json::Value = resp.json().await?;
    let results = body["organic"].as_array()
        .map(|arr| arr.iter().take(10).filter_map(|item| {
            Some(SearchResult {
                title: item["title"].as_str()?.to_string(),
                url: item["link"].as_str()?.to_string(),
                snippet: item["snippet"].as_str().unwrap_or("").to_string(),
            })
        }).collect())
        .unwrap_or_default();
    Ok(results)
}
// task 28: health check
#[tauri::command]
pub async fn health_check(provider: String, endpoint: Option<String>) -> Result<bool, AppError> {
    let client = reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(5))
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| AppError::Network(e.to_string()))?;
    let url = match provider.as_str() {
        "claude" => "https://api.anthropic.com/v1/messages".to_string(),
        "openai" => "https://api.openai.com/v1/models".to_string(),
        "gemini" => "https://generativelanguage.googleapis.com/v1beta/models".to_string(),
        "ollama" => format!("{}/api/tags", endpoint.as_deref().unwrap_or("http://localhost:11434")),
        "lmstudio" => format!("{}/v1/models", endpoint.as_deref().unwrap_or("http://localhost:1234")),
        _ => return Err(AppError::Provider(format!("unknown provider: {provider}"))),
    };
    match client.get(&url).send().await {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}
