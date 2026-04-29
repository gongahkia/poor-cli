//! Multi-provider completion runtime.
//!
//! Builds on [`crate::completion::CompletionProvider`] by adding:
//!   - additional built-in providers (history, alias).
//!   - a `RankedRunner` that runs many providers, isolates panics, dedups,
//!     and re-ranks the merged list with `wok-fuzzy`.
//!
//! Existing single-provider call sites (`gather_completions`) are untouched;
//! consumers opt in by switching to `RankedRunner::run`.

use std::panic::{catch_unwind, AssertUnwindSafe};

use wok_fuzzy::score as fuzzy_score;

use crate::completion::{CompletionContext, CompletionItem, CompletionKind, CompletionProvider};

/// Run multiple providers w/ panic isolation + fuzzy reranking.
pub struct RankedRunner {
    providers: Vec<Box<dyn CompletionProvider + Send + Sync>>,
    max_results: usize,
}

impl RankedRunner {
    /// Build a runner.
    pub fn new(max_results: usize) -> Self {
        Self {
            providers: Vec::new(),
            max_results: max_results.max(1),
        }
    }

    /// Append a provider.
    pub fn with(mut self, p: Box<dyn CompletionProvider + Send + Sync>) -> Self {
        self.providers.push(p);
        self
    }

    /// Run all providers, dedup by `text`, re-rank by fuzzy score against
    /// `ctx.word`, return up to `max_results`.
    pub fn run(&self, ctx: &CompletionContext) -> Vec<CompletionItem> {
        let mut merged: Vec<CompletionItem> = Vec::new();
        for provider in &self.providers {
            let items = catch_unwind(AssertUnwindSafe(|| provider.complete(ctx)))
                .unwrap_or_default();
            merged.extend(items);
        }
        // dedup preserving first occurrence.
        let mut seen = std::collections::HashSet::new();
        merged.retain(|item| seen.insert(item.text.clone()));

        if ctx.word.is_empty() {
            merged.truncate(self.max_results);
            return merged;
        }

        let mut scored: Vec<(f64, CompletionItem)> = merged
            .into_iter()
            .filter_map(|item| {
                fuzzy_score(&ctx.word, &item.text).map(|score| (score, item))
            })
            .collect();
        scored.sort_by(|a, b| b.0.total_cmp(&a.0));
        scored.truncate(self.max_results);
        scored.into_iter().map(|(_, item)| item).collect()
    }
}

/// History-backed completer. Holds an immutable list of past commands.
pub struct HistoryProvider {
    entries: Vec<String>,
}

impl HistoryProvider {
    /// Wrap a history list.
    pub fn new(entries: Vec<String>) -> Self {
        Self { entries }
    }
}

impl CompletionProvider for HistoryProvider {
    fn complete(&self, ctx: &CompletionContext) -> Vec<CompletionItem> {
        if ctx.input.is_empty() {
            return Vec::new();
        }
        self.entries
            .iter()
            .rev()
            .filter(|line| line.starts_with(&ctx.input))
            .take(64)
            .map(|line| CompletionItem {
                text: line.clone(),
                description: "history".into(),
                kind: CompletionKind::Argument,
            })
            .collect()
    }
}

/// Alias-backed completer. Pairs of `(name, expansion)`.
pub struct AliasProvider {
    aliases: Vec<(String, String)>,
}

impl AliasProvider {
    /// Build from `(name, expansion)` pairs.
    pub fn new(aliases: Vec<(String, String)>) -> Self {
        Self { aliases }
    }
}

impl CompletionProvider for AliasProvider {
    fn complete(&self, ctx: &CompletionContext) -> Vec<CompletionItem> {
        // aliases only complete the first token of a line.
        if ctx.word_start != 0 {
            return Vec::new();
        }
        self.aliases
            .iter()
            .filter(|(name, _)| name.starts_with(&ctx.word))
            .map(|(name, expansion)| CompletionItem {
                text: name.clone(),
                description: format!("alias → {expansion}"),
                kind: CompletionKind::Command,
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx(input: &str, word: &str) -> CompletionContext {
        let cursor = input.len();
        let word_start = input.rfind(word).unwrap_or(0);
        let word_end = word_start + word.len();
        CompletionContext {
            input: input.into(),
            cursor,
            word: word.into(),
            word_start,
            word_end,
        }
    }

    struct StaticProvider(Vec<&'static str>);
    impl CompletionProvider for StaticProvider {
        fn complete(&self, _ctx: &CompletionContext) -> Vec<CompletionItem> {
            self.0
                .iter()
                .map(|s| CompletionItem {
                    text: (*s).to_string(),
                    description: String::new(),
                    kind: CompletionKind::Argument,
                })
                .collect()
        }
    }

    struct PanickyProvider;
    impl CompletionProvider for PanickyProvider {
        fn complete(&self, _ctx: &CompletionContext) -> Vec<CompletionItem> {
            panic!("provider blew up");
        }
    }

    #[test]
    fn history_filters_by_prefix() {
        let p = HistoryProvider::new(vec![
            "git status".into(),
            "git push".into(),
            "ls -la".into(),
        ]);
        let items = p.complete(&ctx("git", "git"));
        let texts: Vec<_> = items.iter().map(|i| i.text.as_str()).collect();
        // newest first (reverse order)
        assert_eq!(texts, vec!["git push", "git status"]);
    }

    #[test]
    fn alias_only_completes_first_token() {
        let p = AliasProvider::new(vec![("g".into(), "git".into()), ("ll".into(), "ls -la".into())]);
        // first-token match
        let items = p.complete(&ctx("g", "g"));
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].text, "g");
        // mid-line word (word_start != 0): no aliases
        let mut c = ctx("echo g", "g");
        c.word_start = 5;
        let items = p.complete(&c);
        assert!(items.is_empty());
    }

    #[test]
    fn ranked_runner_panic_isolation() {
        let r = RankedRunner::new(10)
            .with(Box::new(PanickyProvider))
            .with(Box::new(StaticProvider(vec!["alpha", "beta", "gamma"])));
        // would panic if isolation broken
        let items = r.run(&ctx("a", "a"));
        let texts: Vec<_> = items.iter().map(|i| i.text.as_str()).collect();
        assert!(texts.contains(&"alpha"), "got {texts:?}");
    }

    #[test]
    fn ranked_runner_dedups_and_reranks() {
        let r = RankedRunner::new(10)
            .with(Box::new(StaticProvider(vec!["foo", "foobar"])))
            .with(Box::new(StaticProvider(vec!["foo", "barfoo"])));
        let items = r.run(&ctx("foo", "foo"));
        let texts: Vec<_> = items.iter().map(|i| i.text.as_str()).collect();
        // "foo" appears once
        assert_eq!(texts.iter().filter(|t| **t == "foo").count(), 1);
        // best match for "foo" should rank first
        assert_eq!(texts[0], "foo");
    }

    #[test]
    fn ranked_runner_truncates_to_max() {
        let many: Vec<&'static str> = vec!["aa", "ab", "ac", "ad", "ae"];
        let r = RankedRunner::new(2).with(Box::new(StaticProvider(many)));
        let items = r.run(&ctx("a", "a"));
        assert_eq!(items.len(), 2);
    }

    #[test]
    fn empty_word_skips_fuzzy_filter() {
        let r = RankedRunner::new(10)
            .with(Box::new(StaticProvider(vec!["alpha", "beta", "gamma"])));
        let items = r.run(&ctx("", ""));
        assert_eq!(items.len(), 3);
    }
}
