//! Workflow templates for reusable parameterized commands.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::history::fuzzy_score;

/// One workflow parameter definition.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct WorkflowParam {
    /// Parameter name.
    pub name: String,
    /// Placeholder text shown to users.
    #[serde(default)]
    pub placeholder: String,
    /// Default value used when available.
    #[serde(default)]
    pub default: Option<String>,
    /// User-facing parameter description.
    #[serde(default)]
    pub description: String,
}

/// One named workflow template.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct Workflow {
    /// Workflow name.
    pub name: String,
    /// Human-readable summary.
    #[serde(default)]
    pub description: String,
    /// Command template text.
    pub template: String,
    /// Parameter metadata.
    #[serde(default)]
    pub params: Vec<WorkflowParam>,
}

impl Workflow {
    /// Render the workflow template with default values when provided.
    pub fn render_with_defaults(&self) -> String {
        let mut rendered = self.template.clone();
        for (idx, param) in self.params.iter().enumerate() {
            let Some(default) = &param.default else {
                continue;
            };
            let positional = format!("${}", idx + 1);
            let named = format!("${{{}}}", param.name);
            rendered = rendered.replace(&positional, default);
            rendered = rendered.replace(&named, default);
        }
        rendered
    }
}

/// In-memory workflow registry.
#[derive(Debug, Clone, Default)]
pub struct WorkflowStore {
    workflows: Vec<Workflow>,
}

impl WorkflowStore {
    /// Create an empty workflow store.
    pub fn new() -> Self {
        Self {
            workflows: Vec::new(),
        }
    }

    /// Return all workflows in insertion order.
    pub fn workflows(&self) -> &[Workflow] {
        &self.workflows
    }

    /// Load workflow files from a directory.
    pub fn load_from_dir(&mut self, dir: &Path) {
        let Ok(entries) = fs::read_dir(dir) else {
            return;
        };

        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_file() || path.extension().is_none_or(|ext| ext != "toml") {
                continue;
            }
            let Ok(content) = fs::read_to_string(&path) else {
                continue;
            };
            let Ok(workflow) = toml::from_str::<Workflow>(&content) else {
                continue;
            };
            self.add(workflow);
        }
    }

    /// Add or replace a workflow by name.
    pub fn add(&mut self, workflow: Workflow) {
        self.remove(&workflow.name);
        self.workflows.push(workflow);
    }

    /// Remove a workflow by name.
    pub fn remove(&mut self, name: &str) -> bool {
        let before = self.workflows.len();
        self.workflows.retain(|workflow| workflow.name != name);
        self.workflows.len() != before
    }

    /// Find workflows matching the query with fuzzy ranking.
    pub fn find(&self, query: &str) -> Vec<&Workflow> {
        let query = query.trim();
        if query.is_empty() {
            return self.workflows.iter().collect();
        }

        let mut ranked = self
            .workflows
            .iter()
            .filter_map(|workflow| {
                let score_name = fuzzy_score(&workflow.name, query);
                let score_desc = fuzzy_score(&workflow.description, query);
                score_name
                    .into_iter()
                    .chain(score_desc)
                    .max()
                    .map(|score| (workflow, score))
            })
            .collect::<Vec<_>>();
        ranked.sort_by(|(_, left), (_, right)| right.cmp(left));
        ranked.into_iter().map(|(workflow, _)| workflow).collect()
    }

    /// Lookup one workflow by name.
    pub fn by_name(&self, name: &str) -> Option<&Workflow> {
        self.workflows.iter().find(|workflow| workflow.name == name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_with_defaults_replaces_named_and_positional() {
        let workflow = Workflow {
            name: "deploy".to_string(),
            description: String::new(),
            template: "git push origin ${branch} && cargo test $1".to_string(),
            params: vec![WorkflowParam {
                name: "branch".to_string(),
                placeholder: "main".to_string(),
                default: Some("main".to_string()),
                description: String::new(),
            }],
        };

        assert_eq!(
            workflow.render_with_defaults(),
            "git push origin main && cargo test main"
        );
    }

    #[test]
    fn test_find_returns_fuzzy_matches() {
        let mut store = WorkflowStore::new();
        store.add(Workflow {
            name: "deploy".to_string(),
            description: "deploy to prod".to_string(),
            template: "echo deploy".to_string(),
            params: Vec::new(),
        });
        store.add(Workflow {
            name: "test".to_string(),
            description: "run tests".to_string(),
            template: "cargo test".to_string(),
            params: Vec::new(),
        });

        let matches = store.find("depl");
        assert_eq!(
            matches.first().map(|workflow| workflow.name.as_str()),
            Some("deploy")
        );
    }
}
