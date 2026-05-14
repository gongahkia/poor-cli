use crate::types::StreamChunk;
use futures_util::StreamExt;
use reqwest::Response;
use tauri::{AppHandle, Emitter};
pub async fn stream_sse(app: &AppHandle, event_name: &str, response: Response) -> Result<String, crate::error::AppError> {
    let mut full_content = String::new();
    let mut stream = response.bytes_stream();
    let mut buffer = String::new();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| crate::error::AppError::Network(e.to_string()))?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));
        while let Some(pos) = buffer.find('\n') {
            let line = buffer[..pos].to_string();
            buffer = buffer[pos + 1..].to_string();
            if let Some(data) = line.strip_prefix("data: ") {
                if data == "[DONE]" {
                    let _ = app.emit(event_name, StreamChunk { delta: String::new(), done: true });
                    return Ok(full_content);
                }
                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(data) {
                    if let Some(delta) = extract_delta(&parsed) {
                        full_content.push_str(&delta);
                        let _ = app.emit(event_name, StreamChunk { delta, done: false });
                    }
                }
            }
        }
    }
    let _ = app.emit(event_name, StreamChunk { delta: String::new(), done: true });
    Ok(full_content)
}
fn extract_delta(v: &serde_json::Value) -> Option<String> {
    // openai/lmstudio format
    if let Some(d) = v.pointer("/choices/0/delta/content").and_then(|v| v.as_str()) {
        return Some(d.to_string());
    }
    // anthropic format
    if let Some(d) = v.pointer("/delta/text").and_then(|v| v.as_str()) {
        return Some(d.to_string());
    }
    // gemini format
    if let Some(d) = v.pointer("/candidates/0/content/parts/0/text").and_then(|v| v.as_str()) {
        return Some(d.to_string());
    }
    None
}
