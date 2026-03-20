use std::collections::HashMap;
use std::sync::LazyLock;

use serde::Deserialize;

const CATALOG_JSON: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../poor_cli/provider_catalog.json"
));

#[derive(Clone, Debug, Deserialize)]
struct ProviderCatalog {
    providers: HashMap<String, ProviderSpec>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderSpec {
    display_name: String,
    env_var: String,
    default_model: String,
    common_models: Vec<String>,
    setup_help: String,
    capability_summary: String,
    #[allow(dead_code)]
    base_url: Option<String>,
    aliases: Option<Vec<String>>,
}

static PROVIDER_CATALOG: LazyLock<ProviderCatalog> = LazyLock::new(|| {
    serde_json::from_str(CATALOG_JSON).expect("provider catalog must be valid JSON")
});

fn canonical_provider_name(name: &str) -> Option<&'static str> {
    let normalized = name.trim().to_ascii_lowercase();
    for (provider_name, spec) in &PROVIDER_CATALOG.providers {
        if provider_name == &normalized {
            return Some(provider_name.as_str());
        }
        if spec.aliases.as_ref().is_some_and(|aliases| {
            aliases
                .iter()
                .any(|alias| alias.eq_ignore_ascii_case(&normalized))
        }) {
            return Some(provider_name.as_str());
        }
    }
    None
}

fn provider_spec(name: &str) -> Option<&'static ProviderSpec> {
    let canonical = canonical_provider_name(name)?;
    PROVIDER_CATALOG.providers.get(canonical)
}

pub fn default_model(name: &str) -> &'static str {
    provider_spec(name)
        .map(|spec| spec.default_model.as_str())
        .unwrap_or("unknown")
}

pub fn common_models(name: &str) -> Vec<String> {
    provider_spec(name)
        .map(|spec| spec.common_models.clone())
        .unwrap_or_default()
}

pub fn setup_help(name: &str) -> &'static str {
    provider_spec(name)
        .map(|spec| spec.setup_help.as_str())
        .unwrap_or("")
}

pub fn env_var(name: &str) -> &'static str {
    provider_spec(name)
        .map(|spec| spec.env_var.as_str())
        .unwrap_or("")
}

pub fn display_name(name: &str) -> &'static str {
    provider_spec(name)
        .map(|spec| spec.display_name.as_str())
        .unwrap_or("Provider")
}

pub fn capability_summary(name: &str) -> &'static str {
    provider_spec(name)
        .map(|spec| spec.capability_summary.as_str())
        .unwrap_or("")
}
