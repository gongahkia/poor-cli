//! URL detection and clickable links in terminal output.

/// A detected URL span in a line of text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UrlSpan {
    /// Start column.
    pub col_start: u16,
    /// End column (exclusive).
    pub col_end: u16,
    /// The URL string.
    pub url: String,
}

/// Detect URLs in a line of text.
pub fn detect_urls(line_text: &str) -> Vec<UrlSpan> {
    let mut spans = Vec::new();
    let mut start = 0;

    while start < line_text.len() {
        if let Some(pos) = find_url_start(&line_text[start..]) {
            let abs_start = start + pos;
            let url_end = find_url_end(&line_text[abs_start..]);
            let url = &line_text[abs_start..abs_start + url_end];

            if url.len() > 8 {
                // Minimum: https://x
                spans.push(UrlSpan {
                    col_start: abs_start as u16,
                    col_end: (abs_start + url_end) as u16,
                    url: url.to_string(),
                });
            }

            start = abs_start + url_end;
        } else {
            break;
        }
    }

    spans
}

fn find_url_start(text: &str) -> Option<usize> {
    text.find("https://")
        .or_else(|| text.find("http://"))
}

fn find_url_end(text: &str) -> usize {
    let url_chars: &[char] = &[' ', '\t', '\n', '"', '\'', '<', '>', '{', '}', '|', '\\', '^', '[', ']', '`'];
    text.find(url_chars).unwrap_or(text.len())
}

/// Open a URL in the default browser.
pub fn open_url(url: &str) {
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("open").arg(url).spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = std::process::Command::new("xdg-open").arg(url).spawn();
    }
    #[cfg(target_os = "windows")]
    {
        let _ = std::process::Command::new("cmd")
            .args(["/c", "start", url])
            .spawn();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_url() {
        let urls = detect_urls("visit https://example.com today");
        assert_eq!(urls.len(), 1);
        assert_eq!(urls[0].url, "https://example.com");
    }

    #[test]
    fn test_detect_url_with_path() {
        let urls = detect_urls("see https://example.com/path?q=1#section");
        assert_eq!(urls.len(), 1);
        assert!(urls[0].url.contains("/path?q=1#section"));
    }

    #[test]
    fn test_no_url() {
        let urls = detect_urls("no urls here");
        assert!(urls.is_empty());
    }

    #[test]
    fn test_bare_protocol_ignored() {
        let urls = detect_urls("http:// alone");
        assert!(urls.is_empty()); // too short
    }
}
