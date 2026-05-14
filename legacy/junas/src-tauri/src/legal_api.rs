use crate::error::AppError;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LegalSearchResult {
    pub title: String,
    pub url: String,
    pub snippet: String,
    pub source: String,
}

const SSO_BASE: &str = "https://sso.agc.gov.sg";
const COMMONLII_BASE: &str = "https://www.commonlii.org";
const REQUEST_TIMEOUT_SECS: u64 = 15;

fn build_client() -> Result<reqwest::Client, AppError> {
    reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(10))
        .timeout(std::time::Duration::from_secs(REQUEST_TIMEOUT_SECS))
        .user_agent("Junas/0.1 (legal-research-tool)")
        .build()
        .map_err(|e| AppError::Network(e.to_string()))
}

/// search Singapore Statutes Online (sso.agc.gov.sg) via HTML scraping
#[tauri::command]
pub async fn search_sso_statutes(query: String) -> Result<Vec<LegalSearchResult>, AppError> {
    let client = build_client()?;
    let url = format!("{}/Search/Content?SearchPhrase={}&Category=Acts", SSO_BASE, urlencoding(& query));
    let response = client.get(&url).send().await?;
    if !response.status().is_success() {
        return Err(AppError::Network(format!("SSO returned HTTP {}", response.status())));
    }
    let html = response.text().await.map_err(|e| AppError::Network(e.to_string()))?;
    Ok(parse_sso_results(&html, &query))
}

/// search CommonLII Singapore case law
#[tauri::command]
pub async fn search_commonlii_cases(query: String) -> Result<Vec<LegalSearchResult>, AppError> {
    let client = build_client()?;
    let url = format!(
        "{}/cgi-bin/sinosrch.cgi?method=auto&query={}&meta=%2Fsg&mask_path=",
        COMMONLII_BASE,
        urlencoding(&query)
    );
    let response = client.get(&url).send().await?;
    if !response.status().is_success() {
        return Err(AppError::Network(format!("CommonLII returned HTTP {}", response.status())));
    }
    let html = response.text().await.map_err(|e| AppError::Network(e.to_string()))?;
    Ok(parse_commonlii_results(&html))
}

fn urlencoding(s: &str) -> String {
    s.chars().map(|c| match c {
        ' ' => '+'.to_string(),
        c if c.is_alphanumeric() || "-_.~".contains(c) => c.to_string(),
        c => format!("%{:02X}", c as u32),
    }).collect()
}

fn parse_sso_results(html: &str, query: &str) -> Vec<LegalSearchResult> {
    let mut results = Vec::new();
    // parse search result entries from SSO HTML
    // SSO uses <div class="search-result-item"> or similar patterns
    for segment in html.split("<a ").skip(1) {
        if results.len() >= 10 { break; }
        let href = extract_attr(segment, "href");
        let text = extract_text_content(segment);
        if href.is_empty() || text.is_empty() { continue; }
        if !text.to_lowercase().contains(&query.to_lowercase().chars().take(20).collect::<String>())
            && !href.contains("/Act/") && !href.contains("/SL/") { continue; }
        let full_url = if href.starts_with("http") { href.clone() } else { format!("{}{}", SSO_BASE, href) };
        if !full_url.contains("sso.agc.gov.sg") && !full_url.contains("/Act/") { continue; }
        results.push(LegalSearchResult {
            title: text.chars().take(200).collect(),
            url: full_url,
            snippet: format!("Singapore statute matching '{}'", query),
            source: "SSO".to_string(),
        });
    }
    results
}

fn parse_commonlii_results(html: &str) -> Vec<LegalSearchResult> {
    let mut results = Vec::new();
    // CommonLII search results are in <li> tags with <a href> and text
    for segment in html.split("<li>").skip(1) {
        if results.len() >= 10 { break; }
        if let Some(a_start) = segment.find("<a ") {
            let a_segment = &segment[a_start..];
            let href = extract_attr(a_segment, "href");
            let title = extract_text_content(a_segment);
            if href.is_empty() || title.is_empty() { continue; }
            let full_url = if href.starts_with("http") { href.clone() } else {
                format!("{}{}", COMMONLII_BASE, href)
            };
            // extract snippet from text after the link
            let snippet = segment.split("</a>").nth(1)
                .map(|s| strip_html_tags(s).chars().take(300).collect::<String>())
                .unwrap_or_default();
            results.push(LegalSearchResult {
                title: strip_html_tags(&title).chars().take(200).collect(),
                url: full_url,
                snippet: snippet.trim().to_string(),
                source: "CommonLII".to_string(),
            });
        }
    }
    results
}

fn extract_attr(html: &str, attr: &str) -> String {
    let pattern = format!("{}=\"", attr);
    if let Some(start) = html.find(&pattern) {
        let rest = &html[start + pattern.len()..];
        if let Some(end) = rest.find('"') {
            return rest[..end].to_string();
        }
    }
    String::new()
}

fn extract_text_content(html: &str) -> String {
    let end = html.find("</a>").unwrap_or(html.len().min(500));
    let segment = &html[..end];
    // find the > that closes the opening tag
    if let Some(gt) = segment.find('>') {
        return strip_html_tags(&segment[gt + 1..]).trim().to_string();
    }
    String::new()
}

fn strip_html_tags(html: &str) -> String {
    let mut result = String::with_capacity(html.len());
    let mut in_tag = false;
    for c in html.chars() {
        match c {
            '<' => in_tag = true,
            '>' => in_tag = false,
            _ if !in_tag => result.push(c),
            _ => {}
        }
    }
    result
}
