use super::super::*;

pub(crate) fn format_status_view_payload(
    payload: &Value,
    app: &App,
    watch_state: &WatchState,
    qa_watch_state: &QaWatchState,
) -> String {
    let session = payload.get("session").unwrap_or(&Value::Null);
    let provider = payload.pointer("/provider/active").unwrap_or(&Value::Null);
    let context = payload
        .pointer("/context/lastPreview")
        .unwrap_or(&Value::Null);
    let runs = payload.pointer("/runs/recent").unwrap_or(&Value::Null);
    let collab = payload.get("collaboration").unwrap_or(&Value::Null);
    let mutation = payload
        .pointer("/recovery/lastMutation")
        .unwrap_or(&Value::Null);
    let recent_run_id = runs
        .as_array()
        .and_then(|items| items.first())
        .and_then(|run| run.get("runId"))
        .and_then(|value| value.as_str())
        .unwrap_or("-");
    let selected_count = context
        .get("selected")
        .and_then(|value| value.as_array())
        .map(|items| items.len())
        .unwrap_or(0);
    let excluded_count = context
        .get("excluded")
        .and_then(|value| value.as_array())
        .map(|items| items.len())
        .unwrap_or(0);
    let context_total = context
        .get("totalTokens")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let context_budget = context
        .get("budgetTokens")
        .and_then(|value| value.as_u64())
        .unwrap_or(app.context_budget_tokens as u64);
    let role = collab
        .get("role")
        .and_then(|value| value.as_str())
        .unwrap_or("solo");
    let room = collab
        .get("room")
        .and_then(|value| value.as_str())
        .unwrap_or("-");
    let member_count = collab
        .get("memberCount")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let mut lines = vec![
        "**Session Status**".to_string(),
        format!(
            "- Provider: `{}/{}`",
            provider.get("name").and_then(|value| value.as_str()).unwrap_or("-"),
            provider.get("model").and_then(|value| value.as_str()).unwrap_or("-")
        ),
        format!(
            "- Routing mode: `{}`",
            session
                .get("routingMode")
                .and_then(|value| value.as_str())
                .unwrap_or("manual")
        ),
        format!(
            "- Permission mode: `{}`",
            session
                .get("permissionMode")
                .and_then(|value| value.as_str())
                .unwrap_or("prompt")
        ),
        format!("- CWD: `{}`", app.cwd),
        format!("- Response mode: `{}`", app.response_mode.as_str()),
        format!("- Context: {selected_count} selected / {excluded_count} excluded (~{context_total}/{context_budget} tokens)"),
        format!("- Recent run: `{recent_run_id}`"),
        format!("- Watch mode: {}", if watch_state.is_running() { "active" } else { "inactive" }),
        format!("- QA watch: {}", if qa_watch_state.is_running() { "running" } else { "stopped" }),
        format!("- Collaboration: role=`{role}` room=`{room}` members={member_count}"),
    ];
    if let Some(intent) = mutation.get("intent").and_then(|value| value.as_str()) {
        if !intent.is_empty() {
            lines.push(format!("- Last mutation: `{intent}`"));
        }
    }
    lines.join("\n")
}

pub(crate) fn format_trust_view_payload(payload: &Value) -> String {
    let trust = payload.get("trust").unwrap_or(&Value::Null);
    let provider = payload.pointer("/provider/active").unwrap_or(&Value::Null);
    let readiness = payload
        .pointer("/provider/readiness")
        .unwrap_or(&Value::Null);
    let recovery = payload.get("recovery").unwrap_or(&Value::Null);
    let mut lines = vec![
        "**Trust Center**".to_string(),
        format!(
            "- Provider: `{}/{}`",
            provider
                .get("name")
                .and_then(|value| value.as_str())
                .unwrap_or("-"),
            provider
                .get("model")
                .and_then(|value| value.as_str())
                .unwrap_or("-")
        ),
        format!(
            "- Routing mode: `{}`",
            provider
                .get("routingMode")
                .and_then(|value| value.as_str())
                .unwrap_or("manual")
        ),
        format!(
            "- Sandbox preset: `{}`",
            trust
                .get("sandboxPreset")
                .and_then(|value| value.as_str())
                .unwrap_or("-")
        ),
        format!(
            "- Checkpointing: `{}`",
            trust
                .get("checkpointing")
                .and_then(|value| value.as_bool())
                .unwrap_or(false)
        ),
        format!(
            "- Trusted workspace boundary: `{}`",
            trust
                .pointer("/security/trustedWorkspaceBoundary")
                .and_then(|value| value.as_bool())
                .unwrap_or(true)
        ),
        format!(
            "- Privacy posture: `{}`",
            payload
                .pointer("/provider/privacyPosture")
                .and_then(|value| value.as_str())
                .unwrap_or("unknown")
        ),
    ];
    if let Some(fallback_to) = payload
        .pointer("/provider/fallback/to")
        .and_then(|value| value.as_str())
    {
        if !fallback_to.is_empty() {
            lines.push(format!("- Fallback target: `{fallback_to}`"));
        }
    }
    if let Some(last_error) = payload
        .pointer("/provider/lastError")
        .and_then(|value| value.as_str())
    {
        if !last_error.is_empty() {
            lines.push(format!(
                "- Last provider error: {}",
                truncate_line(last_error, 180)
            ));
        }
    }
    if let Some(roots) = trust
        .pointer("/security/trustedRoots")
        .and_then(|value| value.as_array())
    {
        if !roots.is_empty() {
            lines.push(format!("- Trusted roots: {}", roots.len()));
        }
    }
    let hook_total = trust
        .pointer("/policy/hooks/totalHooks")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    lines.push(format!("- Policy hooks: {hook_total}"));
    let hook_validation_errors = trust
        .pointer("/policy/hooks/validationErrors")
        .and_then(|value| value.as_array())
        .map(|items| items.len())
        .unwrap_or(0);
    if hook_validation_errors > 0 {
        lines.push(format!("- Hook validation errors: {hook_validation_errors}"));
    }
    if let Some(obj) = readiness.as_object() {
        let ready_count = obj
            .values()
            .filter(|entry| {
                entry
                    .get("ready")
                    .and_then(|value| value.as_bool())
                    .unwrap_or(false)
            })
            .count();
        lines.push(format!("- Ready providers: {ready_count}"));
    }
    if let Some(checkpoint_id) = recovery
        .pointer("/lastMutation/checkpointId")
        .and_then(|value| value.as_str())
    {
        if !checkpoint_id.is_empty() {
            lines.push(format!("- Last rollback point: `{checkpoint_id}`"));
        }
    }
    lines.join("\n")
}

pub(crate) fn format_doctor_report_payload(payload: &Value) -> String {
    let overall = payload
        .pointer("/summary/overall")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let ready_provider_count = payload
        .pointer("/summary/readyProviderCount")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let routing_mode = payload
        .pointer("/summary/routingMode")
        .and_then(|value| value.as_str())
        .unwrap_or("manual");
    let privacy = payload
        .pointer("/summary/privacyPosture")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let checks = payload
        .get("checks")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    let mut lines = vec![
        "**Doctor Report**".to_string(),
        format!("- Overall: `{overall}`"),
        format!("- Ready providers: {ready_provider_count}"),
        format!("- Routing mode: `{routing_mode}`"),
        format!("- Privacy posture: `{privacy}`"),
        String::new(),
    ];
    for check in checks {
        let title = check
            .get("title")
            .and_then(|value| value.as_str())
            .unwrap_or("Check");
        let status = check
            .get("status")
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let message = check
            .get("message")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        let action = check
            .get("action")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        lines.push(format!("- **{title}** [{status}]: {message}"));
        if !action.is_empty() {
            lines.push(format!("  action: {action}"));
        }
    }
    lines.join("\n")
}

pub(crate) fn format_setup_guide_payload(
    trust_payload: &Value,
    workflows_payload: &Value,
) -> String {
    let provider_readiness = trust_payload
        .pointer("/provider/readiness")
        .unwrap_or(&Value::Null);
    let recommended_workflow = workflows_payload
        .get("recommended")
        .and_then(|value| value.as_str())
        .unwrap_or("implement");
    let recommended_routing = trust_payload
        .pointer("/session/routingMode")
        .and_then(|value| value.as_str())
        .unwrap_or("manual");
    let recommended_sandbox = trust_payload
        .pointer("/trust/sandboxPreset")
        .and_then(|value| value.as_str())
        .unwrap_or("workspace-write");
    let ready_count = provider_readiness
        .as_object()
        .map(|items| {
            items
                .values()
                .filter(|entry| {
                    entry
                        .get("ready")
                        .and_then(|value| value.as_bool())
                        .unwrap_or(false)
                })
                .count()
        })
        .unwrap_or(0);
    let lines = vec![
        "**Setup Guide**".to_string(),
        format!("- Ready providers: {ready_count}"),
        format!("- Recommended routing mode: `{recommended_routing}`"),
        format!("- Recommended sandbox preset: `{recommended_sandbox}`"),
        format!("- Suggested first workflow: `{recommended_workflow}`"),
        String::new(),
        "Next steps:".to_string(),
        "1. Use `/api-key` if a cloud provider is not ready.".to_string(),
        "2. Use `/sandbox <preset>` to confirm your mutation guardrails.".to_string(),
        "3. Run `/workflow <name>` to inspect a starter scaffold.".to_string(),
        "4. Run `/trust` to verify rollback, provider, and policy state.".to_string(),
    ];
    lines.join("\n")
}
