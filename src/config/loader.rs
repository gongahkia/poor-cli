use std::path::{Path, PathBuf};
use serde::Deserialize;
use super::theme::ThemeConfig;

/// Config file structure (Task 43)
#[derive(Debug, Deserialize, Default)]
pub struct ChronConfig {
    pub theme: Option<ThemeConfig>,
    pub export: Option<ExportConfig>,
    pub server: Option<ServerConfig>,
    pub keys: Option<std::collections::HashMap<String, String>>,
}

#[derive(Debug, Deserialize, Default)]
pub struct ExportConfig {
    pub default_format: Option<String>,
    pub default_width: Option<u32>,
    pub default_height: Option<u32>,
    pub default_dpi: Option<u32>,
}

#[derive(Debug, Deserialize, Default)]
pub struct ServerConfig {
    pub port: Option<u16>,
    pub open_browser: Option<bool>,
}

impl ChronConfig {
    /// Load config from standard locations:
    /// 1. .chronrc in current directory
    /// 2. ~/.config/chron/config.toml
    pub fn load(explicit_path: Option<&Path>) -> Self {
        if let Some(p) = explicit_path {
            return Self::load_file(p).unwrap_or_default();
        }

        // Try .chronrc in cwd
        let local = Path::new(".chronrc");
        if local.exists() {
            if let Ok(cfg) = Self::load_file(local) {
                return cfg;
            }
        }

        // Try ~/.config/chron/config.toml
        if let Some(home) = dirs_path() {
            let global = home.join("config.toml");
            if global.exists() {
                if let Ok(cfg) = Self::load_file(&global) {
                    return cfg;
                }
            }
        }

        Self::default()
    }

    fn load_file(path: &Path) -> Result<Self, String> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| format!("failed to read config: {}", e))?;
        toml::from_str(&content)
            .map_err(|e| format!("failed to parse config: {}", e))
    }
}

fn dirs_path() -> Option<PathBuf> {
    std::env::var("HOME").ok()
        .map(|h| PathBuf::from(h).join(".config").join("chron"))
}
