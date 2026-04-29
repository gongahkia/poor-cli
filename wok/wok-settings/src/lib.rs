//! Layered settings store w/ derive macro.
//!
//! Goals:
//!   1. Typed settings struct via `#[derive(Settings)]`.
//!   2. Layered loading: `Defaults < UserToml < EnvOverrides`.
//!   3. Live-reload diff: compare two `T` values and report which fields
//!      changed by name (caller decides whether to apply or warn).
//!
//! Non-goals (yet):
//!   - JSON-schema export. The schema struct is in place; the JSON serializer
//!     can be added when the editor LSP integration starts.
//!
//! See `wok-app/src/config.rs` for the eventual consumer.

#![deny(missing_docs)]

extern crate self as wok_settings;

use std::path::Path;

use serde::de::DeserializeOwned;
use thiserror::Error;

pub use wok_settings_derive::Settings as SettingsDerive;

/// Errors raised by the layered loader.
#[derive(Debug, Error)]
pub enum SettingsError {
    /// Underlying I/O.
    #[error("settings I/O: {0}")]
    Io(#[from] std::io::Error),
    /// TOML parse failure.
    #[error("settings parse: {0}")]
    Parse(#[from] toml::de::Error),
}

/// Implemented automatically by `#[derive(Settings)]`. Implementors expose
/// schema metadata used by layered loading and live-reload diffs.
pub trait Settings: Sized {
    /// Schema describing the field layout.
    fn schema() -> SettingsSchema;
}

/// Static schema description.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SettingsSchema {
    /// Type name of the implementing struct.
    pub type_name: &'static str,
    /// One entry per named field, in declaration order.
    pub fields: Vec<SettingsField>,
}

/// One field in a [`SettingsSchema`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SettingsField {
    /// Field identifier as written in source.
    pub name: &'static str,
    /// Stringified Rust type.
    pub type_name: &'static str,
}

/// One layered source backing a [`SettingsStore`].
#[derive(Debug, Clone)]
pub enum Layer {
    /// Compile-time defaults.
    Defaults,
    /// User TOML on disk (path captured for diagnostics).
    UserToml(std::path::PathBuf),
    /// In-process overrides (e.g., env-var-derived).
    Overrides,
}

/// Diff entry for a single field.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChangedField {
    /// Field name as written in source.
    pub name: &'static str,
    /// Old value rendered as TOML for diagnostics.
    pub old: String,
    /// New value rendered as TOML for diagnostics.
    pub new: String,
}

/// Layered settings store. `T` is the settings struct.
pub struct SettingsStore<T> {
    current: T,
    source: Layer,
}

impl<T> SettingsStore<T>
where
    T: Settings + Default + Clone + DeserializeOwned + serde::Serialize,
{
    /// Construct from defaults only.
    pub fn from_defaults() -> Self {
        Self {
            current: T::default(),
            source: Layer::Defaults,
        }
    }

    /// Load defaults, then merge a user TOML file if it exists.
    pub fn load_with_user_toml(path: &Path) -> Result<Self, SettingsError> {
        if !path.exists() {
            return Ok(Self::from_defaults());
        }
        let text = std::fs::read_to_string(path)?;
        let value: T = toml::from_str(&text)?;
        Ok(Self {
            current: value,
            source: Layer::UserToml(path.to_path_buf()),
        })
    }

    /// Borrow the current value.
    pub fn current(&self) -> &T {
        &self.current
    }

    /// The layer the current value came from.
    pub fn source(&self) -> &Layer {
        &self.source
    }

    /// Replace the current value (e.g., after a hot reload). Returns the diff
    /// between the previous and the new value.
    pub fn replace(&mut self, next: T) -> Vec<ChangedField> {
        let diff = diff(&self.current, &next);
        self.current = next;
        diff
    }
}

/// Compute a per-field diff between `a` and `b`.
///
/// Implementation is value-based: serialize both sides to TOML once and
/// compare top-level table entries by key. This avoids requiring `PartialEq`
/// on every field type and tolerates additions across versions.
pub fn diff<T: Settings + serde::Serialize>(a: &T, b: &T) -> Vec<ChangedField> {
    let schema = T::schema();
    let table_a = to_table(a);
    let table_b = to_table(b);
    let mut out = Vec::new();
    for f in &schema.fields {
        let av = table_a
            .as_ref()
            .and_then(|t| t.get(f.name))
            .cloned()
            .unwrap_or(toml::Value::String(String::new()));
        let bv = table_b
            .as_ref()
            .and_then(|t| t.get(f.name))
            .cloned()
            .unwrap_or(toml::Value::String(String::new()));
        if av != bv {
            out.push(ChangedField {
                name: f.name,
                old: render(&av),
                new: render(&bv),
            });
        }
    }
    out
}

fn to_table<T: serde::Serialize>(value: &T) -> Option<toml::value::Table> {
    let v = toml::Value::try_from(value).ok()?;
    match v {
        toml::Value::Table(t) => Some(t),
        _ => None,
    }
}

fn render(v: &toml::Value) -> String {
    match v {
        toml::Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::{Deserialize, Serialize};

    #[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, SettingsDerive)]
    struct Demo {
        name: String,
        count: u32,
        flag: bool,
    }

    #[test]
    fn schema_lists_fields_in_order() {
        let s = Demo::schema();
        assert_eq!(s.type_name, "Demo");
        assert_eq!(s.fields.len(), 3);
        assert_eq!(s.fields[0].name, "name");
        assert_eq!(s.fields[1].name, "count");
        assert_eq!(s.fields[2].name, "flag");
    }

    #[test]
    fn store_from_defaults() {
        let s = SettingsStore::<Demo>::from_defaults();
        assert_eq!(s.current().count, 0);
        assert!(matches!(s.source(), Layer::Defaults));
    }

    #[test]
    fn load_user_toml_overrides_defaults() {
        let dir = std::env::temp_dir().join(format!(
            "wok-settings-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("c.toml");
        std::fs::write(&path, "name = \"hi\"\ncount = 7\nflag = true\n").unwrap();
        let store = SettingsStore::<Demo>::load_with_user_toml(&path).unwrap();
        assert_eq!(store.current().name, "hi");
        assert_eq!(store.current().count, 7);
        assert!(store.current().flag);
        assert!(matches!(store.source(), Layer::UserToml(_)));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn missing_path_falls_back_to_defaults() {
        let store = SettingsStore::<Demo>::load_with_user_toml(Path::new(
            "/tmp/this-does-not-exist-xyz.toml",
        ))
        .unwrap();
        assert_eq!(store.current(), &Demo::default());
    }

    #[test]
    fn diff_reports_changed_fields_only() {
        let a = Demo {
            name: "a".into(),
            count: 1,
            flag: false,
        };
        let b = Demo {
            name: "b".into(),
            count: 1,
            flag: true,
        };
        let d = diff(&a, &b);
        let names: Vec<_> = d.iter().map(|c| c.name).collect();
        assert_eq!(names, vec!["name", "flag"]);
    }

    #[test]
    fn replace_returns_diff_and_updates() {
        let mut s = SettingsStore::<Demo>::from_defaults();
        let diff = s.replace(Demo {
            name: "next".into(),
            count: 9,
            flag: true,
        });
        assert_eq!(diff.len(), 3);
        assert_eq!(s.current().name, "next");
    }

    #[test]
    fn parse_error_is_surfaced() {
        let dir = std::env::temp_dir().join("wok-settings-bad");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("c.toml");
        std::fs::write(&path, "name = 12345\n").unwrap(); // wrong type
        let r = SettingsStore::<Demo>::load_with_user_toml(&path);
        assert!(matches!(r, Err(SettingsError::Parse(_))));
        std::fs::remove_dir_all(&dir).ok();
    }
}
