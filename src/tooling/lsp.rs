use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

/// Minimal LSP server implementation (Task 55)
/// Handles stdio JSON-RPC for textDocument/completion, diagnostics, hover

#[derive(Debug, Serialize, Deserialize)]
pub struct LspMessage {
    pub jsonrpc: String,
    pub id: Option<Value>,
    pub method: Option<String>,
    pub params: Option<Value>,
    pub result: Option<Value>,
}

/// LSP completion item
#[derive(Debug, Serialize)]
pub struct CompletionItem {
    pub label: String,
    pub kind: u32,
    pub detail: Option<String>,
}

/// LSP diagnostic
#[derive(Debug, Serialize)]
pub struct Diagnostic {
    pub range: Range,
    pub severity: u32,
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct Range {
    pub start: Position,
    pub end: Position,
}

#[derive(Debug, Serialize)]
pub struct Position {
    pub line: u32,
    pub character: u32,
}

/// Get keyword completions for .seuss files
pub fn get_completions(prefix: &str) -> Vec<CompletionItem> {
    let keywords = vec![
        ("timeline", 14, "Declare a timeline"),
        ("entity", 14, "Declare an entity"),
        ("rel", 14, "Declare a relationship"),
        ("type", 14, "Define a custom type"),
        ("if", 14, "Conditional"),
        ("for", 14, "Loop"),
        ("fn", 3, "Function definition"),
        ("import", 14, "Import another file"),
        ("linear", 21, "Timeline kind"),
        ("branch", 21, "Timeline kind"),
        ("parallel", 21, "Timeline kind"),
        ("loop", 21, "Timeline kind"),
        ("nested", 21, "Timeline kind"),
        ("character", 21, "Entity type"),
        ("event", 21, "Entity type"),
        ("location", 21, "Entity type"),
        ("artifact", 21, "Entity type"),
        ("faction", 21, "Entity type"),
    ];

    keywords
        .iter()
        .filter(|(name, _, _)| name.starts_with(prefix))
        .map(|(name, kind, detail)| CompletionItem {
            label: name.to_string(),
            kind: *kind,
            detail: Some(detail.to_string()),
        })
        .collect()
}

/// Get diagnostics from parsing a .seuss file
pub fn get_diagnostics(source: &str, file: &str) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();

    match crate::lang::parser::parse_program(source, file) {
        Ok(program) => {
            let mut evaluator = crate::eval::evaluator::Evaluator::new();
            if let Err(e) = evaluator.eval_program(&program) {
                diagnostics.push(Diagnostic {
                    range: Range {
                        start: Position {
                            line: 0,
                            character: 0,
                        },
                        end: Position {
                            line: 0,
                            character: 0,
                        },
                    },
                    severity: 1, // Error
                    message: e.message,
                });
            }
        }
        Err(errors) => {
            for (i, e) in errors.iter().enumerate() {
                diagnostics.push(Diagnostic {
                    range: Range {
                        start: Position {
                            line: i as u32,
                            character: 0,
                        },
                        end: Position {
                            line: i as u32,
                            character: 0,
                        },
                    },
                    severity: 1,
                    message: e.to_string(),
                });
            }
        }
    }

    diagnostics
}

/// Get hover info for an entity name
pub fn get_hover_info(source: &str, file: &str, word: &str) -> Option<String> {
    let program = crate::lang::parser::parse_program(source, file).ok()?;
    let mut evaluator = crate::eval::evaluator::Evaluator::new();
    evaluator.eval_program(&program).ok()?;

    // Look up entity by name
    for ent in evaluator.world.entities.values() {
        if ent.name == word {
            let mut info = format!("**{}** : {}\n\n", ent.name, ent.type_id);
            for (k, v) in &ent.attributes {
                info.push_str(&format!("- {}: {}\n", k, v));
            }
            return Some(info);
        }
    }

    // Look up timeline
    for tl in evaluator.world.timelines.values() {
        if tl.name == word {
            return Some(format!("**timeline {}** ({:?})", tl.name, tl.kind));
        }
    }

    None
}
