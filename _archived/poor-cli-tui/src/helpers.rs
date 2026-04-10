use std::path::Path;

pub fn first_line(text: &str) -> String {
    text.lines().next().unwrap_or("").trim().to_string()
}

pub fn truncate_line(text: &str, max_chars: usize) -> String {
    let mut out = String::new();
    for (i, ch) in text.chars().enumerate() {
        if i >= max_chars {
            out.push('…');
            return out;
        }
        out.push(ch);
    }
    out
}

pub fn truncate_block(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    let mut out = String::new();
    for (i, ch) in text.chars().enumerate() {
        if i >= max_chars {
            out.push_str("\n... (truncated)");
            break;
        }
        out.push(ch);
    }
    out
}

pub fn detect_project_traits(root: &Path) -> Vec<&'static str> {
    let mut traits = Vec::new();
    if root.join("Cargo.toml").is_file() {
        traits.push("rust");
    }
    if root.join("pyproject.toml").is_file()
        || root.join("requirements.txt").is_file()
        || root.join("setup.py").is_file()
    {
        traits.push("python");
    }
    if root.join("package.json").is_file() {
        traits.push("javascript");
    }
    traits
}

pub fn should_skip_dir(name: &str) -> bool {
    matches!(
        name,
        ".git" | "target" | "node_modules" | ".venv" | "venv" | "__pycache__"
    )
}

pub fn classify_project_kind(root: &Path) -> String {
    let traits = detect_project_traits(root);
    if traits.is_empty() {
        return "generic".to_string();
    }
    if traits.len() == 1 {
        return traits[0].to_string();
    }
    "mixed".to_string()
}
