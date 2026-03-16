use std::collections::HashSet;
use std::sync::LazyLock;

use serde::Deserialize;

const MANIFEST_JSON: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../poor_cli/command_manifest.json"
));

#[derive(Clone, Debug, Deserialize)]
struct CommandManifest {
    notes: Vec<String>,
    commands: Vec<SlashCommandSpec>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SlashCommandSpec {
    pub command: String,
    pub description: String,
    pub recommended: bool,
    pub category: String,
}

static MANIFEST: LazyLock<CommandManifest> = LazyLock::new(|| {
    serde_json::from_str(MANIFEST_JSON).expect("command manifest must be valid JSON")
});

pub static SLASH_COMMANDS: LazyLock<Vec<SlashCommandSpec>> = LazyLock::new(|| {
    let mut seen = HashSet::new();
    let mut commands = Vec::new();
    for command in &MANIFEST.commands {
        assert!(
            seen.insert(command.command.clone()),
            "duplicate slash command in manifest: {}",
            command.command
        );
        commands.push(command.clone());
    }
    commands
});

static HELP_MARKDOWN: LazyLock<String> = LazyLock::new(render_help_markdown);

pub fn help_markdown() -> &'static str {
    HELP_MARKDOWN.as_str()
}

fn render_help_markdown() -> String {
    let mut lines = vec!["**Available Commands**".to_string(), String::new()];
    for note in &MANIFEST.notes {
        lines.push(format!("{note}  "));
    }
    lines.push(String::new());

    let mut categories = Vec::new();
    for command in &*SLASH_COMMANDS {
        if !categories.contains(&command.category.as_str()) {
            categories.push(command.category.as_str());
        }
    }

    for category in categories {
        lines.push(format!("**{category}:**"));
        for command in SLASH_COMMANDS.iter().filter(|entry| entry.category == category) {
            lines.push(format!("- `{}` - {}", command.command, command.description));
        }
        lines.push(String::new());
    }

    lines.join("\n").trim_end().to_string()
}

#[cfg(test)]
mod tests {
    use super::{help_markdown, SLASH_COMMANDS};
    use std::collections::HashSet;

    #[test]
    fn slash_commands_are_unique() {
        let unique: HashSet<_> = SLASH_COMMANDS.iter().map(|spec| spec.command.as_str()).collect();
        assert_eq!(unique.len(), SLASH_COMMANDS.len());
    }

    #[test]
    fn help_markdown_includes_tasking_and_sandbox() {
        let rendered = help_markdown();
        assert!(rendered.contains("`/task`"));
        assert!(rendered.contains("`/sandbox`"));
        assert!(rendered.contains("`/skills`"));
    }
}
