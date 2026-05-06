//! Ranked subsequence fuzzy matching.
//!
//! Scoring rules (highest first):
//!   1. Substring hit at position 0 (prefix exact).
//!   2. Substring hit elsewhere — closer-to-start beats farther.
//!   3. Subsequence — every query char appears in order. Bonuses for:
//!      - matches at word boundaries (after `_`, `-`, ` `, `/`, `.`, or
//!        camelCase transition lower→upper).
//!      - contiguous runs (consecutive matched chars).
//!      - earlier overall position.
//!
//! Matching is case-insensitive (ASCII lowercased).
//!
//! Returns `None` when the query is not a subsequence of the candidate.

#![deny(missing_docs)]

/// Numeric score. Higher = better. Always `>= 0.0` when returned via `Some`.
pub type Score = f64;

/// Score `query` against `candidate`. Returns `None` if no match.
pub fn score(query: &str, candidate: &str) -> Option<Score> {
    if query.is_empty() {
        return Some(0.0);
    }
    let q = query.to_ascii_lowercase();
    let c_lower = candidate.to_ascii_lowercase();

    // Tier 1+2: substring.
    if let Some(pos) = c_lower.find(&q) {
        let prefix_bonus = if pos == 0 { 100.0 } else { 0.0 };
        let position_bonus = 100.0 / (pos as f64 + 1.0);
        return Some(1000.0 + prefix_bonus + position_bonus);
    }

    // Tier 3: subsequence with boundary + contiguity bonuses.
    subsequence_score(&q, candidate)
}

fn subsequence_score(query: &str, candidate: &str) -> Option<Score> {
    let cand_chars: Vec<char> = candidate.chars().collect();
    let q_chars: Vec<char> = query.chars().collect();

    let mut total: f64 = 0.0;
    let mut ci = 0usize;
    let mut last_match: Option<usize> = None;

    for &qc in &q_chars {
        let mut found = None;
        while ci < cand_chars.len() {
            if cand_chars[ci].eq_ignore_ascii_case(&qc) {
                found = Some(ci);
                break;
            }
            ci += 1;
        }
        let idx = found?;

        let mut bonus = 10.0;
        // Boundary bonus.
        if idx == 0 || is_boundary(cand_chars[idx - 1], cand_chars[idx]) {
            bonus += 8.0;
        }
        // Contiguity bonus.
        if let Some(prev) = last_match {
            if idx == prev + 1 {
                bonus += 6.0;
            }
        }
        // Position bonus (earlier is better).
        bonus -= idx as f64 * 0.1;

        total += bonus;
        last_match = Some(idx);
        ci = idx + 1;
    }

    Some(total.max(0.0))
}

fn is_boundary(prev: char, curr: char) -> bool {
    matches!(prev, '_' | '-' | ' ' | '/' | '.' | ':' | '\\')
        || (prev.is_ascii_lowercase() && curr.is_ascii_uppercase())
}

/// Ranked match result for an indexed candidate.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Match {
    /// Index of the candidate in the input slice.
    pub index: usize,
    /// Computed score.
    pub score: Score,
}

/// Score every candidate; return matches sorted by score desc, then by original
/// index asc as a stable tie-break.
pub fn match_many<S: AsRef<str>>(query: &str, candidates: &[S]) -> Vec<Match> {
    let mut out: Vec<Match> = candidates
        .iter()
        .enumerate()
        .filter_map(|(i, c)| score(query, c.as_ref()).map(|s| Match { index: i, score: s }))
        .collect();
    out.sort_by(|a, b| {
        b.score
            .total_cmp(&a.score)
            .then_with(|| a.index.cmp(&b.index))
    });
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_query_matches_everything() {
        assert_eq!(score("", "anything"), Some(0.0));
    }

    #[test]
    fn no_match_returns_none() {
        assert!(score("xyz", "abc").is_none());
    }

    #[test]
    fn prefix_beats_midmatch() {
        let prefix = score("foo", "foobar").unwrap();
        let mid = score("foo", "barfoo").unwrap();
        assert!(prefix > mid, "prefix {prefix} not > mid {mid}");
    }

    #[test]
    fn substring_beats_subsequence() {
        let sub = score("abc", "xabcx").unwrap();
        let seq = score("abc", "axbxc").unwrap();
        assert!(sub > seq);
    }

    #[test]
    fn boundary_bonus_applies() {
        // 'b' after '_' boundary > 'b' embedded.
        let bound = score("ab", "a_bb").unwrap();
        let embed = score("ab", "axbb").unwrap();
        assert!(bound > embed, "bound {bound} embed {embed}");
    }

    #[test]
    fn camelcase_boundary_counts() {
        let camel = score("ab", "aBig").unwrap();
        let flat = score("ab", "axbig").unwrap();
        assert!(camel > flat);
    }

    #[test]
    fn case_insensitive() {
        assert!(score("FOO", "foobar").is_some());
        assert!(score("foo", "FOOBAR").is_some());
    }

    #[test]
    fn match_many_sorts_desc_then_index() {
        let cs = ["barfoo", "foobar", "fboaor"];
        let m = match_many("foo", &cs);
        assert_eq!(m[0].index, 1, "got {m:?}");
        assert!(m.windows(2).all(|w| w[0].score >= w[1].score));
    }

    #[test]
    fn match_many_drops_non_matches() {
        let cs = ["abc", "xyz", "axbxc"];
        let m = match_many("abc", &cs);
        assert_eq!(m.len(), 2);
    }

    #[test]
    fn unicode_passthrough_is_safe() {
        // We only ASCII-fold, but unicode chars must not panic.
        assert!(score("ä", "äbc").is_some());
    }

    #[test]
    fn contiguous_beats_split() {
        let cont = score("abc", "abc_xy").unwrap();
        let split = score("abc", "a_b_c_").unwrap();
        assert!(cont > split, "cont {cont} split {split}");
    }
}
