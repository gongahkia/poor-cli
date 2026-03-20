use super::super::*;

pub(super) fn format_mcp_status(payload: &Value) -> String {
    let configured = payload
        .get("configuredServers")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let connected = payload
        .get("connectedServers")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let tool_count = payload
        .get("toolCount")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let mut lines = vec![
        format!("**MCP Status**"),
        format!("- Connected servers: {connected}/{configured}"),
        format!("- Registered tools: {tool_count}"),
    ];

    if let Some(servers) = payload.get("servers").and_then(|v| v.as_object()) {
        for (name, entry) in servers {
            let enabled = entry
                .get("enabled")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            let connected = entry
                .get("connected")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let tools = entry
                .get("registeredTools")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                })
                .unwrap_or_default();
            let error = entry
                .get("error")
                .and_then(|v| v.as_str())
                .filter(|value| !value.is_empty())
                .unwrap_or("");
            lines.push(format!(
                "- `{name}`: enabled=`{enabled}` connected=`{connected}` tools=`{}`{}",
                if tools.is_empty() {
                    "-"
                } else {
                    tools.as_str()
                },
                if error.is_empty() {
                    String::new()
                } else {
                    format!(" error=`{error}`")
                }
            ));
        }
    }

    lines.join("\n")
}

pub(super) fn parse_mcp_tool_names(raw: &str) -> Vec<Value> {
    raw.split(|ch: char| ch == ',' || ch.is_whitespace())
        .filter(|value| !value.trim().is_empty())
        .map(|value| Value::String(value.trim().to_string()))
        .collect()
}

pub(super) fn format_instruction_stack(payload: &Value) -> String {
    let source_count = payload
        .get("sourceCount")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let mut lines = vec![
        format!("**Instruction Stack**"),
        format!("- Sources: {source_count}"),
    ];

    if let Some(sources) = payload.get("sources").and_then(|v| v.as_array()) {
        for source in sources {
            let kind = source
                .get("kind")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let label = source
                .get("label")
                .and_then(|v| v.as_str())
                .unwrap_or("(unnamed)");
            let path = source.get("path").and_then(|v| v.as_str()).unwrap_or("");
            let content = source.get("content").and_then(|v| v.as_str()).unwrap_or("");
            lines.push(format!(
                "- `{kind}` {label}{}",
                if path.is_empty() {
                    String::new()
                } else {
                    format!(" (`{path}`)")
                }
            ));
            if !content.is_empty() {
                lines.push(format!("  {}", truncate_block(content, 180)));
            }
        }
    }

    lines.join("\n")
}

pub(super) fn format_policy_status(payload: &Value) -> String {
    let hooks_dir = payload
        .pointer("/hooks/hooksDir")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let total_hooks = payload
        .pointer("/hooks/totalHooks")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let audit_enabled = payload
        .pointer("/audit/enabled")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let audit_path = payload
        .pointer("/audit/path")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let validation_errors = payload
        .pointer("/hooks/validationErrors")
        .and_then(|v| v.as_array())
        .map(|items| items.len())
        .unwrap_or(0);
    let supported_schema_versions = payload
        .pointer("/hooks/supportedSchemaVersions")
        .and_then(|v| v.as_array())
        .map(|items| {
            items.iter()
                .filter_map(|item| item.as_u64())
                .map(|value| value.to_string())
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_default();

    let mut lines = vec![
        "**Policy Status**".to_string(),
        format!("- Hooks: {total_hooks}"),
        format!("- Hooks dir: `{hooks_dir}`"),
        format!(
            "- Audit: {}{}",
            if audit_enabled { "enabled" } else { "disabled" },
            if audit_path.is_empty() {
                String::new()
            } else {
                format!(" (`{audit_path}`)")
            }
        ),
    ];
    if !supported_schema_versions.is_empty() {
        lines.push(format!("- Supported schema versions: {supported_schema_versions}"));
    }
    if validation_errors > 0 {
        lines.push(format!("- Validation errors: {validation_errors}"));
    }

    if let Some(events) = payload.pointer("/hooks/events").and_then(|v| v.as_object()) {
        for (event, entries) in events {
            let count = entries.as_array().map(|items| items.len()).unwrap_or(0);
            lines.push(format!("- `{event}`: {count} hook(s)"));
        }
    }

    lines.join("\n")
}
