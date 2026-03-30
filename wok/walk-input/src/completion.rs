//! Completion providers for the owned input editor.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Completion item type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CompletionKind {
    /// Executable command from `$PATH`.
    Command,
    /// Filesystem path.
    FilePath,
    /// Environment variable.
    EnvVar,
    /// Generic argument suggestion.
    Argument,
}

/// One completion candidate shown in the popup.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompletionItem {
    /// Text inserted into the editor if selected.
    pub text: String,
    /// Human-readable metadata.
    pub description: String,
    /// Candidate kind.
    pub kind: CompletionKind,
}

/// Context passed to completion providers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompletionContext {
    /// Full input text.
    pub input: String,
    /// Cursor byte index into `input`.
    pub cursor: usize,
    /// Current token under completion.
    pub word: String,
    /// Start byte index of `word`.
    pub word_start: usize,
    /// End byte index of `word`.
    pub word_end: usize,
}

/// Trait implemented by completion providers.
pub trait CompletionProvider {
    /// Return completion candidates for the current context.
    fn complete(&self, context: &CompletionContext) -> Vec<CompletionItem>;
}

/// File and directory completion provider.
#[derive(Debug, Default)]
pub struct PathCompletionProvider;

impl CompletionProvider for PathCompletionProvider {
    fn complete(&self, context: &CompletionContext) -> Vec<CompletionItem> {
        if context.word.is_empty() {
            return Vec::new();
        }

        let original = context.word.as_str();
        let expanded = expand_tilde(original);
        let path = Path::new(&expanded);

        let (dir, prefix, had_separator) = split_path_prefix(path, original);
        let Ok(entries) = fs::read_dir(&dir) else {
            return Vec::new();
        };

        let mut items = Vec::new();
        for entry in entries.flatten() {
            let file_name = entry.file_name();
            let file_name = file_name.to_string_lossy();
            if !file_name.starts_with(&prefix) {
                continue;
            }

            let meta = entry.metadata().ok();
            let kind = if meta.as_ref().is_some_and(std::fs::Metadata::is_dir) {
                "dir"
            } else {
                "file"
            };
            let size = meta
                .as_ref()
                .map(std::fs::Metadata::len)
                .unwrap_or_default();

            let mut completion = if had_separator {
                format!("{}{}", normalize_dir_prefix(original), file_name)
            } else {
                file_name.to_string()
            };
            if kind == "dir" {
                completion.push('/');
            }

            items.push(CompletionItem {
                text: completion,
                description: format!("{kind} • {size} bytes"),
                kind: CompletionKind::FilePath,
            });
        }

        items.sort_by(|left, right| left.text.cmp(&right.text));
        items.truncate(128);
        items
    }
}

/// Command completion provider backed by `$PATH` scanning.
#[derive(Debug, Default)]
pub struct CommandCompletionProvider {
    cache: Mutex<Option<Vec<(String, String)>>>,
}

impl CommandCompletionProvider {
    fn ensure_cache(&self) -> Vec<(String, String)> {
        let mut cache = self.cache.lock().unwrap();
        if let Some(cached) = cache.as_ref() {
            return cached.clone();
        }

        let mut commands = Vec::new();
        let mut seen = HashSet::new();
        let path_dirs = std::env::var_os("PATH")
            .map(|value| std::env::split_paths(&value).collect::<Vec<_>>())
            .unwrap_or_default();
        for dir in path_dirs {
            let Ok(entries) = fs::read_dir(&dir) else {
                continue;
            };
            for entry in entries.flatten() {
                let path = entry.path();
                if !path.is_file() {
                    continue;
                }
                let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
                    continue;
                };
                if !seen.insert(name.to_string()) {
                    continue;
                }
                commands.push((name.to_string(), path.display().to_string()));
            }
        }

        commands.sort_by(|left, right| left.0.cmp(&right.0));
        *cache = Some(commands.clone());
        commands
    }
}

impl CompletionProvider for CommandCompletionProvider {
    fn complete(&self, context: &CompletionContext) -> Vec<CompletionItem> {
        let prefix = context.word.to_ascii_lowercase();
        if prefix.is_empty() {
            return Vec::new();
        }

        let mut items = self
            .ensure_cache()
            .into_iter()
            .filter(|(command, _)| command.to_ascii_lowercase().starts_with(&prefix))
            .map(|(command, path)| CompletionItem {
                text: command,
                description: path,
                kind: CompletionKind::Command,
            })
            .collect::<Vec<_>>();

        items.truncate(128);
        items
    }
}

/// Environment-variable completion provider.
#[derive(Debug, Default)]
pub struct EnvVarCompletionProvider;

impl CompletionProvider for EnvVarCompletionProvider {
    fn complete(&self, context: &CompletionContext) -> Vec<CompletionItem> {
        let Some(prefix) = context.word.strip_prefix('$') else {
            return Vec::new();
        };

        let mut items = std::env::vars()
            .filter(|(name, _)| name.starts_with(prefix))
            .map(|(name, value)| CompletionItem {
                text: format!("${name}"),
                description: truncate_value(&value, 40),
                kind: CompletionKind::EnvVar,
            })
            .collect::<Vec<_>>();

        items.sort_by(|left, right| left.text.cmp(&right.text));
        items.truncate(128);
        items
    }
}

/// Merge and rank completion candidates from all providers.
pub fn gather_completions(
    context: &CompletionContext,
    providers: &[&dyn CompletionProvider],
) -> Vec<CompletionItem> {
    let mut items = Vec::new();
    let mut seen = HashSet::new();

    for provider in providers {
        for item in provider.complete(context) {
            if seen.insert(item.text.clone()) {
                items.push(item);
            }
        }
    }

    items.sort_by(|left, right| left.text.cmp(&right.text));
    items
}

/// Build a completion context from editor text and cursor offset.
pub fn completion_context(text: &str, cursor: usize) -> CompletionContext {
    let cursor = cursor.min(text.len());
    let bytes = text.as_bytes();

    let mut start = cursor;
    while start > 0 && !bytes[start - 1].is_ascii_whitespace() {
        start -= 1;
    }

    let mut end = cursor;
    while end < bytes.len() && !bytes[end].is_ascii_whitespace() {
        end += 1;
    }

    CompletionContext {
        input: text.to_string(),
        cursor,
        word: text[start..cursor].to_string(),
        word_start: start,
        word_end: end,
    }
}

fn split_path_prefix(path: &Path, original: &str) -> (PathBuf, String, bool) {
    if original.ends_with('/') {
        return (path.to_path_buf(), String::new(), true);
    }

    if let Some(parent) = path.parent() {
        let had_separator = original.contains('/');
        let prefix = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default()
            .to_string();
        return (parent.to_path_buf(), prefix, had_separator);
    }

    (
        PathBuf::from("."),
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default()
            .to_string(),
        false,
    )
}

fn normalize_dir_prefix(original: &str) -> String {
    if let Some(index) = original.rfind('/') {
        return original[..=index].to_string();
    }
    String::new()
}

fn expand_tilde(path: &str) -> String {
    if let Some(rest) = path.strip_prefix("~/") {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home).join(rest).display().to_string();
        }
    }
    if path == "~" {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home).display().to_string();
        }
    }
    path.to_string()
}

fn truncate_value(value: &str, max: usize) -> String {
    let mut output = value.chars().take(max).collect::<String>();
    if value.chars().count() > max {
        output.push_str("...");
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_completion_context_extracts_word() {
        let context = completion_context("cargo tes", 9);
        assert_eq!(context.word, "tes");
        assert_eq!(context.word_start, 6);
    }

    #[test]
    fn test_env_provider_requires_dollar_prefix() {
        let provider = EnvVarCompletionProvider;
        let context = CompletionContext {
            input: "HOME".to_string(),
            cursor: 4,
            word: "HOME".to_string(),
            word_start: 0,
            word_end: 4,
        };
        assert!(provider.complete(&context).is_empty());
    }
}
