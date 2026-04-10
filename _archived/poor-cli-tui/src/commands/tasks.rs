use super::super::*;

pub(crate) fn format_task_detail(payload: &Value) -> String {
    let task = payload.get("task").unwrap_or(payload);
    let task_id = task
        .get("taskId")
        .and_then(|value| value.as_str())
        .unwrap_or("(unknown)");
    let status = task
        .get("status")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let title = task
        .get("title")
        .and_then(|value| value.as_str())
        .unwrap_or("(untitled)");
    let preset = task
        .get("sandboxPreset")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let source = task
        .get("source")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let worktree = task
        .get("worktreePath")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let artifact_dir = task
        .get("artifactDir")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let summary = task
        .get("summary")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let error_message = task
        .get("errorMessage")
        .and_then(|value| value.as_str())
        .unwrap_or("");

    let mut lines = vec![
        format!("**Task** `{task_id}`"),
        format!("- Status: `{status}`"),
        format!("- Title: {title}"),
        format!("- Sandbox: `{preset}`"),
        format!("- Source: `{source}`"),
    ];
    if !worktree.is_empty() {
        lines.push(format!("- Worktree: `{worktree}`"));
    }
    if !artifact_dir.is_empty() {
        lines.push(format!("- Artifacts: `{artifact_dir}`"));
    }
    if !summary.is_empty() {
        lines.push(format!("- Summary: {}", truncate_line(summary, 180)));
    }
    if !error_message.is_empty() {
        lines.push(format!("- Error: {}", truncate_line(error_message, 180)));
    }
    if let Some(runs) = payload.get("runs").and_then(|value| value.as_array()) {
        if let Some(run) = runs.first() {
            if let Some(run_id) = run.get("runId").and_then(|value| value.as_str()) {
                let status = run
                    .get("status")
                    .and_then(|value| value.as_str())
                    .unwrap_or("unknown");
                lines.push(format!("- Latest run: `{run_id}` [{status}]"));
            }
        }
    }
    lines.join("\n")
}

pub(crate) fn format_runs_payload(payload: &Value, title: &str) -> String {
    let runs = payload
        .get("runs")
        .or_else(|| payload.get("recent"))
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    if runs.is_empty() {
        return format!("{title}\n\nNo runs found.");
    }

    let mut lines = vec![title.to_string(), String::new()];
    for run in runs {
        let run_id = run
            .get("runId")
            .and_then(|value| value.as_str())
            .unwrap_or("(unknown)");
        let status = run
            .get("status")
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let source_kind = run
            .get("sourceKind")
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let source_id = run
            .get("sourceId")
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let summary = run
            .get("summary")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        let error_class = run
            .get("errorClass")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        lines.push(format!(
            "- `{run_id}` [{status}] `{source_kind}/{source_id}`"
        ));
        if !summary.is_empty() {
            lines.push(format!("  {}", truncate_line(summary, 180)));
        }
        if !error_class.is_empty() {
            lines.push(format!("  error class: `{error_class}`"));
        }
    }
    lines.join("\n")
}

pub(crate) fn format_workflow_detail(payload: &Value) -> String {
    let workflow = payload.get("workflow").unwrap_or(payload);
    let name = workflow
        .get("name")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let description = workflow
        .get("description")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let scaffold = workflow
        .get("starterPrompt")
        .or_else(|| workflow.get("starter_prompt"))
        .or_else(|| workflow.get("promptScaffold"))
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let sandbox = workflow
        .get("defaultSandboxPreset")
        .or_else(|| workflow.get("sandboxPreset"))
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let context = workflow
        .get("contextStrategy")
        .or_else(|| workflow.get("suggestedContextStrategy"))
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let follow_ups = workflow
        .get("followUpCommands")
        .and_then(|value| value.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_default();

    let mut lines = vec![
        format!("**Workflow** `{name}`"),
        format!("- Description: {description}"),
    ];
    if !sandbox.is_empty() {
        lines.push(format!("- Default sandbox: `{sandbox}`"));
    }
    if !context.is_empty() {
        lines.push(format!("- Context strategy: {context}"));
    }
    if !follow_ups.is_empty() {
        lines.push(format!("- Follow-up commands: {follow_ups}"));
    }
    if !scaffold.is_empty() {
        lines.push(String::new());
        lines.push("```text".to_string());
        lines.push(scaffold.to_string());
        lines.push("```".to_string());
    }
    lines.join("\n")
}
