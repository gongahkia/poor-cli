//! Parsers and models for unified Git diffs.

/// One parsed unified diff row.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiffDisplayRow {
    /// Row kind.
    pub kind: DiffRowKind,
    /// Old-file line number, when present.
    pub old_line_number: Option<usize>,
    /// New-file line number, when present.
    pub new_line_number: Option<usize>,
    /// Old-file text, when present.
    pub old_text: Option<String>,
    /// New-file text, when present.
    pub new_text: Option<String>,
    /// Display text including diff prefix for normal rows.
    pub text: String,
}

/// Diff row category.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiffRowKind {
    /// Hunk header row.
    Hunk,
    /// Unchanged context row.
    Context,
    /// Added row.
    Addition,
    /// Deleted row.
    Deletion,
    /// Synthetic collapsed-context marker.
    Collapsed,
}

/// Parsed unified diff rows plus aggregate counts.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedDiffRows {
    /// Parsed rows.
    pub rows: Vec<DiffDisplayRow>,
    /// Number of added lines.
    pub additions: usize,
    /// Number of deleted lines.
    pub deletions: usize,
}

/// Parse display rows from a unified diff patch.
///
/// File headers before the first hunk are skipped. The parser tracks old/new
/// line numbers per hunk and counts addition/deletion rows.
pub fn parse_rows(patch: &str) -> ParsedDiffRows {
    let mut rows = Vec::new();
    let mut old_line_number = 0usize;
    let mut new_line_number = 0usize;
    let mut in_hunk = false;
    let mut additions = 0usize;
    let mut deletions = 0usize;

    for line in patch.lines() {
        if line.starts_with("@@") {
            in_hunk = true;
            let (old_start, new_start) = parse_hunk_header(line);
            old_line_number = old_start;
            new_line_number = new_start;
            rows.push(DiffDisplayRow {
                kind: DiffRowKind::Hunk,
                old_line_number: None,
                new_line_number: None,
                old_text: None,
                new_text: None,
                text: line.to_string(),
            });
            continue;
        }

        if !in_hunk {
            continue;
        }

        if let Some(content) = line.strip_prefix(' ') {
            rows.push(DiffDisplayRow {
                kind: DiffRowKind::Context,
                old_line_number: Some(old_line_number),
                new_line_number: Some(new_line_number),
                old_text: Some(content.to_string()),
                new_text: Some(content.to_string()),
                text: format!(" {content}"),
            });
            old_line_number += 1;
            new_line_number += 1;
            continue;
        }

        if let Some(content) = line.strip_prefix('-') {
            rows.push(DiffDisplayRow {
                kind: DiffRowKind::Deletion,
                old_line_number: Some(old_line_number),
                new_line_number: None,
                old_text: Some(content.to_string()),
                new_text: None,
                text: format!("-{content}"),
            });
            old_line_number += 1;
            deletions += 1;
            continue;
        }

        if let Some(content) = line.strip_prefix('+') {
            rows.push(DiffDisplayRow {
                kind: DiffRowKind::Addition,
                old_line_number: None,
                new_line_number: Some(new_line_number),
                old_text: None,
                new_text: Some(content.to_string()),
                text: format!("+{content}"),
            });
            new_line_number += 1;
            additions += 1;
        }
    }

    ParsedDiffRows {
        rows,
        additions,
        deletions,
    }
}

/// Collapse long runs of context rows while preserving nearby context.
pub fn collapse_context_rows(rows: &[DiffDisplayRow]) -> Vec<DiffDisplayRow> {
    let mut output = Vec::new();
    let mut index = 0usize;
    let leading_context = 3usize;
    let trailing_context = 3usize;
    let collapse_threshold = 12usize;

    while index < rows.len() {
        let row = &rows[index];
        if row.kind != DiffRowKind::Context {
            output.push(row.clone());
            index += 1;
            continue;
        }

        let mut end = index;
        while end < rows.len() && rows[end].kind == DiffRowKind::Context {
            end += 1;
        }

        let run_length = end - index;
        if run_length <= collapse_threshold {
            output.extend_from_slice(&rows[index..end]);
        } else {
            let start_keep_end = index + leading_context;
            let end_keep_start = end - trailing_context;
            output.extend_from_slice(&rows[index..start_keep_end]);
            output.push(DiffDisplayRow {
                kind: DiffRowKind::Collapsed,
                old_line_number: None,
                new_line_number: None,
                old_text: None,
                new_text: None,
                text: format!(
                    "{} unmodified lines",
                    run_length - leading_context - trailing_context
                ),
            });
            output.extend_from_slice(&rows[end_keep_start..end]);
        }

        index = end;
    }

    output
}

/// Parse old/new starting line numbers from a hunk header.
pub fn parse_hunk_header(line: &str) -> (usize, usize) {
    let mut parts = line.split_whitespace();
    let Some("@@") = parts.next() else {
        return (0, 0);
    };
    let Some(old_part) = parts.next() else {
        return (0, 0);
    };
    let Some(new_part) = parts.next() else {
        return (0, 0);
    };
    (parse_hunk_number(old_part), parse_hunk_number(new_part))
}

/// Parse the starting line number from `-10,5` or `+3`.
pub fn parse_hunk_number(token: &str) -> usize {
    let cleaned = token.trim_matches(|ch| matches!(ch, '-' | '+' | ','));
    cleaned
        .split(',')
        .next()
        .and_then(|start| start.parse::<usize>().ok())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(kind: DiffRowKind, text: impl Into<String>, number: usize) -> DiffDisplayRow {
        let text = text.into();
        DiffDisplayRow {
            kind,
            old_line_number: Some(number),
            new_line_number: Some(number),
            old_text: Some(text.clone()),
            new_text: Some(text.clone()),
            text,
        }
    }

    #[test]
    fn parse_empty_patch_returns_empty() {
        let result = parse_rows("");
        assert!(result.rows.is_empty());
        assert_eq!(result.additions, 0);
        assert_eq!(result.deletions, 0);
    }

    #[test]
    fn parse_rows_skips_pre_hunk_lines() {
        let patch = "diff --git a/file.rs b/file.rs\nindex abc..def 100644\n--- a/file.rs\n+++ b/file.rs\n@@ -1,3 +1,3 @@\n context\n-old\n+new\n";
        let result = parse_rows(patch);
        assert_eq!(result.rows.len(), 4);
        assert_eq!(result.rows[0].kind, DiffRowKind::Hunk);
    }

    #[test]
    fn parse_single_hunk_reads_all_row_kinds() {
        let patch = "@@ -10,4 +10,4 @@\n context line\n-deleted line\n+added line\n more context\n";
        let result = parse_rows(patch);
        assert_eq!(result.rows.len(), 5);
        assert_eq!(result.rows[0].kind, DiffRowKind::Hunk);
        assert_eq!(result.rows[1].kind, DiffRowKind::Context);
        assert_eq!(result.rows[1].old_line_number, Some(10));
        assert_eq!(result.rows[1].new_line_number, Some(10));
        assert_eq!(result.rows[2].kind, DiffRowKind::Deletion);
        assert_eq!(result.rows[2].old_line_number, Some(11));
        assert_eq!(result.rows[2].new_line_number, None);
        assert_eq!(result.rows[3].kind, DiffRowKind::Addition);
        assert_eq!(result.rows[3].old_line_number, None);
        assert_eq!(result.rows[3].new_line_number, Some(11));
        assert_eq!(result.rows[4].old_line_number, Some(12));
        assert_eq!(result.rows[4].new_line_number, Some(12));
        assert_eq!(result.additions, 1);
        assert_eq!(result.deletions, 1);
    }

    #[test]
    fn parse_additions_only() {
        let patch = "@@ -5,2 +5,4 @@\n existing\n+new1\n+new2\n existing2\n";
        let result = parse_rows(patch);
        let additions: Vec<_> = result
            .rows
            .iter()
            .filter(|row| row.kind == DiffRowKind::Addition)
            .collect();
        assert_eq!(result.additions, 2);
        assert_eq!(result.deletions, 0);
        assert_eq!(additions[0].new_line_number, Some(6));
        assert_eq!(additions[1].new_line_number, Some(7));
    }

    #[test]
    fn parse_deletions_only() {
        let patch = "@@ -5,4 +5,2 @@\n existing\n-removed1\n-removed2\n existing2\n";
        let result = parse_rows(patch);
        let deletions: Vec<_> = result
            .rows
            .iter()
            .filter(|row| row.kind == DiffRowKind::Deletion)
            .collect();
        assert_eq!(result.additions, 0);
        assert_eq!(result.deletions, 2);
        assert_eq!(deletions[0].old_line_number, Some(6));
        assert_eq!(deletions[1].old_line_number, Some(7));
    }

    #[test]
    fn parse_multiple_hunks_resets_line_numbers() {
        let patch = "@@ -1,3 +1,3 @@\n a\n-b\n+c\n@@ -20,3 +20,3 @@\n x\n-y\n+z\n";
        let result = parse_rows(patch);
        let hunks = result
            .rows
            .iter()
            .filter(|row| row.kind == DiffRowKind::Hunk)
            .count();
        let deletions: Vec<_> = result
            .rows
            .iter()
            .filter(|row| row.kind == DiffRowKind::Deletion)
            .collect();
        let additions: Vec<_> = result
            .rows
            .iter()
            .filter(|row| row.kind == DiffRowKind::Addition)
            .collect();
        assert_eq!(hunks, 2);
        assert_eq!(deletions[1].old_line_number, Some(21));
        assert_eq!(additions[1].new_line_number, Some(21));
    }

    #[test]
    fn parse_captures_text_content() {
        let result = parse_rows("@@ -1,3 +1,3 @@\n context\n-old\n+new\n");
        assert_eq!(result.rows[1].text, " context");
        assert_eq!(result.rows[1].old_text.as_deref(), Some("context"));
        assert_eq!(result.rows[1].new_text.as_deref(), Some("context"));
        assert_eq!(result.rows[2].text, "-old");
        assert_eq!(result.rows[2].old_text.as_deref(), Some("old"));
        assert_eq!(result.rows[2].new_text, None);
        assert_eq!(result.rows[3].text, "+new");
        assert_eq!(result.rows[3].old_text, None);
        assert_eq!(result.rows[3].new_text.as_deref(), Some("new"));
    }

    #[test]
    fn collapse_preserves_short_runs() {
        let rows: Vec<_> = (0..12)
            .map(|i| row(DiffRowKind::Context, format!("line {i}"), i))
            .collect();
        let collapsed = collapse_context_rows(&rows);
        assert_eq!(collapsed.len(), 12);
        assert!(collapsed.iter().all(|row| row.kind == DiffRowKind::Context));
    }

    #[test]
    fn collapse_collapses_long_runs() {
        let rows: Vec<_> = (0..20)
            .map(|i| row(DiffRowKind::Context, format!("line {i}"), i))
            .collect();
        let collapsed = collapse_context_rows(&rows);
        assert_eq!(collapsed.len(), 7);
        assert_eq!(collapsed[3].kind, DiffRowKind::Collapsed);
        assert_eq!(collapsed[3].text, "14 unmodified lines");
    }

    #[test]
    fn collapse_preserves_non_context_rows() {
        let rows = vec![
            DiffDisplayRow {
                kind: DiffRowKind::Hunk,
                old_line_number: None,
                new_line_number: None,
                old_text: None,
                new_text: None,
                text: "@@ -1,1 +1,1 @@".to_string(),
            },
            DiffDisplayRow {
                kind: DiffRowKind::Deletion,
                old_line_number: Some(1),
                new_line_number: None,
                old_text: Some("old".to_string()),
                new_text: None,
                text: "-old".to_string(),
            },
            DiffDisplayRow {
                kind: DiffRowKind::Addition,
                old_line_number: None,
                new_line_number: Some(1),
                old_text: None,
                new_text: Some("new".to_string()),
                text: "+new".to_string(),
            },
        ];
        assert_eq!(collapse_context_rows(&rows), rows);
    }

    #[test]
    fn collapse_handles_mixed_content() {
        let mut rows: Vec<_> = (0..20)
            .map(|i| row(DiffRowKind::Context, i.to_string(), i))
            .collect();
        rows.push(DiffDisplayRow {
            kind: DiffRowKind::Deletion,
            old_line_number: Some(20),
            new_line_number: None,
            old_text: Some("x".to_string()),
            new_text: None,
            text: "-x".to_string(),
        });
        rows.extend((20..40).map(|i| row(DiffRowKind::Context, i.to_string(), i)));

        let collapsed = collapse_context_rows(&rows);
        let markers = collapsed
            .iter()
            .filter(|row| row.kind == DiffRowKind::Collapsed)
            .count();
        assert_eq!(markers, 2);
    }

    #[test]
    fn parse_hunk_header_standard_format() {
        assert_eq!(parse_hunk_header("@@ -10,5 +20,8 @@"), (10, 20));
    }

    #[test]
    fn parse_hunk_header_single_line_format() {
        assert_eq!(parse_hunk_header("@@ -1 +1 @@"), (1, 1));
    }

    #[test]
    fn parse_hunk_header_malformed_returns_zeroes() {
        assert_eq!(parse_hunk_header("@@"), (0, 0));
    }

    #[test]
    fn parse_hunk_number_with_comma() {
        assert_eq!(parse_hunk_number("-10,5"), 10);
    }

    #[test]
    fn parse_hunk_number_without_comma() {
        assert_eq!(parse_hunk_number("+3"), 3);
    }

    #[test]
    fn parse_hunk_number_empty_returns_zero() {
        assert_eq!(parse_hunk_number(""), 0);
    }
}
