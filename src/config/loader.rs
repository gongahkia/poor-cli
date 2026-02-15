use super::theme::ThemeConfig;
use serde::Deserialize;
use std::path::{Path, PathBuf};

/// Config file structure (Task 43)
#[derive(Debug, Deserialize, Default)]
pub struct SeussConfig {
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

impl SeussConfig {
    /// Load config from standard locations:
    /// 1. .seussrc in current directory
    /// 2. ~/.config/seuss/config.toml
    pub fn load(explicit_path: Option<&Path>) -> Self {
        if let Some(p) = explicit_path {
            return Self::load_file(p).unwrap_or_default();
        }

        // Try .seussrc in cwd
        let local = Path::new(".seussrc");
        if local.exists() {
            if let Ok(cfg) = Self::load_file(local) {
                return cfg;
            }
        }

        // Try ~/.config/seuss/config.toml
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
        let content =
            std::fs::read_to_string(path).map_err(|e| format!("failed to read config: {}", e))?;
        toml::from_str(&content).map_err(|e| format!("failed to parse config: {}", e))
    }
}

fn dirs_path() -> Option<PathBuf> {
    std::env::var("HOME")
        .ok()
        .map(|h| PathBuf::from(h).join(".config").join("seuss"))
}
