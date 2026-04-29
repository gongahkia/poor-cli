//! URL detection and clickable links in terminal output.

use std::sync::OnceLock;

use crate::quick_select::{PatternRegistry, PatternType};

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

/// Cell range for one link span.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CellRange {
    /// Absolute row.
    pub row: usize,
    /// Start column (inclusive).
    pub col_start: usize,
    /// End column (exclusive).
    pub col_end: usize,
}

/// Common interface for link types.
pub trait Linkable {
    /// Return the URI target.
    fn uri(&self) -> &str;
    /// Return the occupied cell range.
    fn span(&self) -> CellRange;
}

/// Regex-detected URL link.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DetectedLink {
    /// Link target URI.
    pub uri: String,
    /// Occupied range.
    pub range: CellRange,
}

impl Linkable for DetectedLink {
    fn uri(&self) -> &str {
        &self.uri
    }

    fn span(&self) -> CellRange {
        self.range
    }
}

/// Explicit OSC 8 hyperlink.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExplicitLink {
    /// Link target URI.
    pub uri: String,
    /// Optional OSC 8 id parameter.
    pub id: Option<String>,
    /// Occupied range.
    pub range: CellRange,
}

impl Linkable for ExplicitLink {
    fn uri(&self) -> &str {
        &self.uri
    }

    fn span(&self) -> CellRange {
        self.range
    }
}

/// Detect URLs in a line of text.
pub fn detect_urls(line_text: &str) -> Vec<UrlSpan> {
    static REGISTRY: OnceLock<PatternRegistry> = OnceLock::new();
    let registry = REGISTRY.get_or_init(PatternRegistry::new);
    registry
        .detect_line(0, line_text)
        .into_iter()
        .filter_map(|candidate| {
            matches!(candidate.pattern_type, PatternType::Url).then(|| UrlSpan {
                col_start: candidate.col_start as u16,
                col_end: candidate.col_end as u16,
                url: candidate.text,
            })
        })
        .collect()
}

/// Detect URLs on one terminal row and return link objects.
pub fn detect_links(row: usize, line_text: &str) -> Vec<DetectedLink> {
    detect_urls(line_text)
        .into_iter()
        .map(|span| DetectedLink {
            uri: span.url,
            range: CellRange {
                row,
                col_start: span.col_start as usize,
                col_end: span.col_end as usize,
            },
        })
        .collect()
}

/// Open a URL in the default browser.
pub fn open_url(url: &str) {
    wok_process::open_url(url);
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
