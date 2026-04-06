use super::*;

// ── Blocking RPC helpers ─────────────────────────────────────────────

pub(crate) fn rpc_execute_command_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    command: &str,
) -> Result<String, String> {
    rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, command, None, 60)
}

pub(crate) fn rpc_execute_command_with_timeout_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    command: &str,
    command_timeout_secs: Option<u64>,
    response_timeout_secs: u64,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ExecuteCommand {
            command: command.to_string(),
            timeout: command_timeout_secs,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send command to backend: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(response_timeout_secs))
        .map_err(|_| "Timed out waiting for backend command response".to_string())?
}

pub(crate) fn rpc_read_file_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    file_path: &str,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ReadFile {
            file_path: file_path.to_string(),
            start_line: None,
            end_line: None,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send read_file request: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for backend file read".to_string())?
}

pub(crate) fn rpc_get_config_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetConfig { reply: reply_tx })
        .map_err(|e| format!("Failed to request config: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for backend config".to_string())?
}

pub(crate) fn rpc_get_permissions_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetPermissions { reply: reply_tx })
        .map_err(|e| format!("Failed to request permissions: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for backend permissions".to_string())?
}

pub(crate) fn rpc_set_permissions_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    mode: Option<&str>,
    add_rule: Option<Value>,
    clear_session_rules: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetPermissions {
            mode: mode.map(|value| value.to_string()),
            add_rule,
            clear_session_rules,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request permission update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for permission update".to_string())?
}

pub(crate) fn rpc_get_provider_info_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetProviderInfo { reply: reply_tx })
        .map_err(|e| format!("Failed to request provider info: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for provider info".to_string())?
}

pub(crate) fn rpc_get_tools_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetTools { reply: reply_tx })
        .map_err(|e| format!("Failed to request tools: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for tools".to_string())?
}

pub(crate) fn rpc_get_instruction_stack_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    referenced_files: &[String],
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetInstructionStack {
            referenced_files: referenced_files.to_vec(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request instruction stack: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for instruction stack".to_string())?
}

pub(crate) fn rpc_get_status_view_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetStatusView { reply: reply_tx })
        .map_err(|e| format!("Failed to request status view: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for status view".to_string())?
}

pub(crate) fn rpc_get_trust_view_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetTrustView { reply: reply_tx })
        .map_err(|e| format!("Failed to request trust view: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for trust view".to_string())?
}

pub(crate) fn rpc_get_doctor_report_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetDoctorReport { reply: reply_tx })
        .map_err(|e| format!("Failed to request doctor report: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for doctor report".to_string())?
}

pub(crate) fn rpc_get_policy_status_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetPolicyStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request policy status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for policy status".to_string())?
}

pub(crate) fn rpc_get_sandbox_status_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetSandboxStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request sandbox status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for sandbox status".to_string())?
}

pub(crate) fn rpc_get_mcp_status_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetMcpStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request MCP status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for MCP status".to_string())?
}

pub(crate) fn rpc_gc_checkpoints_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GcCheckpoints { reply: reply_tx })
        .map_err(|e| format!("Failed to request GC: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for GC".to_string())?
}

pub(crate) fn rpc_mcp_health_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::McpHealthCheck { reply: reply_tx })
        .map_err(|e| format!("Failed to request MCP health: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for MCP health".to_string())?
}

pub(crate) fn rpc_get_economy_savings_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetEconomySavings { reply: reply_tx })
        .map_err(|e| format!("Failed to request economy savings: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for economy savings".to_string())?
}

pub(crate) fn rpc_set_economy_preset_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>, preset: &str) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetEconomyPreset { preset: preset.to_string(), reply: reply_tx })
        .map_err(|e| format!("Failed to set economy preset: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for economy preset".to_string())?
}

pub(crate) fn rpc_list_ollama_models_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListOllamaModels { reply: reply_tx })
        .map_err(|e| format!("Failed to request Ollama models: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for Ollama models".to_string())?
}

pub(crate) fn rpc_save_session_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SaveSession { reply: reply_tx })
        .map_err(|e| format!("Failed to save session: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out saving session".to_string())?
}

pub(crate) fn rpc_restore_session_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RestoreSession { reply: reply_tx })
        .map_err(|e| format!("Failed to restore session: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out restoring session".to_string())?
}

pub(crate) fn rpc_list_skills_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListSkills { reply: reply_tx })
        .map_err(|e| format!("Failed to request skills: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for skills".to_string())?
}

pub(crate) fn rpc_get_skill_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetSkill {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request skill: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for skill".to_string())?
}

pub(crate) fn rpc_list_custom_commands_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListCustomCommands { reply: reply_tx })
        .map_err(|e| format!("Failed to request custom commands: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for custom commands".to_string())?
}

pub(crate) fn rpc_get_custom_command_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetCustomCommand {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request custom command: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for custom command".to_string())?
}

pub(crate) fn rpc_run_custom_command_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
    args_text: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RunCustomCommand {
            name: name.to_string(),
            args_text: args_text.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to run custom command: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(120))
        .map_err(|_| "Timed out waiting for custom command".to_string())?
}

pub(crate) fn rpc_get_context_explain_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    message: &str,
    context_files: &[String],
    pinned_context_files: &[String],
    context_budget_tokens: Option<usize>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetContextExplain {
            message: message.to_string(),
            context_files: context_files.to_vec(),
            pinned_context_files: pinned_context_files.to_vec(),
            context_budget_tokens,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request context explanation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for context explanation".to_string())?
}

pub(crate) fn rpc_list_runs_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    source_kind: Option<&str>,
    source_id: Option<&str>,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListRuns {
            source_kind: source_kind.map(|value| value.to_string()),
            source_id: source_id.map(|value| value.to_string()),
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request runs: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for runs".to_string())?
}

pub(crate) fn rpc_list_workflows_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListWorkflows { reply: reply_tx })
        .map_err(|e| format!("Failed to request workflows: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for workflows".to_string())?
}

pub(crate) fn rpc_get_workflow_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetWorkflow {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request workflow: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for workflow".to_string())?
}

pub(crate) fn rpc_list_config_options_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListConfigOptions { reply: reply_tx })
        .map_err(|e| format!("Failed to request config options: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for config options".to_string())?
}

pub(crate) fn rpc_set_config_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    key_path: &str,
    value: Value,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetConfig {
            key_path: key_path.to_string(),
            value,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request config update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for config update".to_string())?
}

pub(crate) fn rpc_toggle_config_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    key_path: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ToggleConfig {
            key_path: key_path.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request config toggle: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for config toggle".to_string())?
}

pub(crate) fn rpc_set_api_key_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    provider: &str,
    api_key: &str,
    persist: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetApiKey {
            provider: provider.to_string(),
            api_key: api_key.to_string(),
            persist,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request API key update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for API key update".to_string())?
}

pub(crate) fn rpc_get_api_key_status_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    provider: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetApiKeyStatus {
            provider: provider.map(|s| s.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request API key status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for API key status".to_string())?
}

pub(crate) fn rpc_initialize_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    provider: Option<&str>,
    model: Option<&str>,
) -> Result<InitResult, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::Initialize {
            provider: provider.map(|value| value.to_string()),
            model: model.map(|value| value.to_string()),
            permission_mode: None,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request backend initialization: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for backend initialization".to_string())?
}

pub(crate) fn rpc_clear_history_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<(), String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ClearHistory { reply: reply_tx })
        .map_err(|e| format!("Failed to request history clear: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for clear history response".to_string())?
}

pub(crate) fn rpc_list_sessions_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListSessions {
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request sessions: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for sessions response".to_string())?
}

pub(crate) fn rpc_list_history_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    count: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListHistory {
            count,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request history: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for history response".to_string())?
}

pub(crate) fn rpc_search_history_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    term: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SearchHistory {
            term: term.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request search: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for search response".to_string())?
}

pub(crate) fn rpc_create_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    title: &str,
    prompt: &str,
    sandbox_preset: &str,
    source: &str,
    auto_start: bool,
    requires_approval: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CreateTask {
            title: title.to_string(),
            prompt: prompt.to_string(),
            sandbox_preset: sandbox_preset.to_string(),
            source: source.to_string(),
            auto_start,
            requires_approval,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to create task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task creation".to_string())?
}

pub(crate) fn rpc_list_tasks_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    inbox_only: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListTasks {
            inbox_only,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to list tasks: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task list".to_string())?
}

pub(crate) fn rpc_get_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to get task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task".to_string())?
}

pub(crate) fn rpc_approve_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ApproveTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to approve task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task approval".to_string())?
}

pub(crate) fn rpc_cancel_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CancelTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to cancel task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task cancel".to_string())?
}

pub(crate) fn rpc_retry_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RetryTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to retry task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task retry".to_string())?
}

pub(crate) fn rpc_replay_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ReplayTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to replay task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task replay".to_string())?
}


pub(crate) fn rpc_get_automation_history_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    automation_id: &str,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetAutomationHistory {
            automation_id: automation_id.to_string(),
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request automation history: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for automation history".to_string())?
}

pub(crate) fn rpc_replay_automation_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    automation_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ReplayAutomation {
            automation_id: automation_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to replay automation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for automation replay".to_string())?
}

pub(crate) fn rpc_list_checkpoints_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListCheckpoints {
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoints: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for checkpoints response".to_string())?
}

pub(crate) fn rpc_create_checkpoint_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    description: &str,
    operation_type: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CreateCheckpoint {
            description: description.to_string(),
            operation_type: operation_type.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoint creation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for checkpoint creation".to_string())?
}

pub(crate) fn rpc_restore_checkpoint_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    checkpoint_id: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RestoreCheckpoint {
            checkpoint_id: checkpoint_id.map(|s| s.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoint restore: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for checkpoint restore".to_string())?
}

pub(crate) fn rpc_preview_checkpoint_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    checkpoint_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::PreviewCheckpoint {
            checkpoint_id: checkpoint_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoint preview: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for checkpoint preview".to_string())?
}

pub(crate) fn rpc_compare_files_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    file1: &str,
    file2: &str,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CompareFiles {
            file1: file1.to_string(),
            file2: file2.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request file comparison: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for file diff response".to_string())?
}

pub(crate) fn rpc_export_conversation_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    export_format: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ExportConversation {
            format: export_format.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request conversation export: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for export response".to_string())?
}

pub(crate) fn rpc_start_host_server_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StartHostServer {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host server start: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for host server start response".to_string())?
}

pub(crate) fn rpc_get_host_server_status_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetHostServerStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request host server status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for host server status response".to_string())?
}

pub(crate) fn rpc_get_collab_summary_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetCollabSummary { reply: reply_tx })
        .map_err(|e| format!("Failed to request collaboration summary: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for collaboration summary".to_string())?
}

pub(crate) fn rpc_stop_host_server_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StopHostServer { reply: reply_tx })
        .map_err(|e| format!("Failed to request host server stop: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host server stop response".to_string())?
}

pub(crate) fn rpc_list_host_members_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListHostMembers {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host members: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host members response".to_string())?
}

pub(crate) fn rpc_list_room_members_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListRoomMembers {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request room members: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for room members response".to_string())?
}

pub(crate) fn rpc_remove_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RemoveHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host member removal: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host member removal response".to_string())?
}

pub(crate) fn rpc_kick_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::KickMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request member kick: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for member kick response".to_string())?
}

pub(crate) fn rpc_set_host_member_role_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    role: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHostMemberRole {
            connection_id: connection_id.to_string(),
            role: role.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host role update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host role update response".to_string())?
}

pub(crate) fn rpc_set_host_lobby_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    enabled: bool,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHostLobby {
            enabled,
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host lobby update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host lobby update response".to_string())?
}

pub(crate) fn rpc_approve_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ApproveHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host member approval: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host member approval response".to_string())?
}

pub(crate) fn rpc_deny_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::DenyHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host member denial: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host member denial response".to_string())?
}

pub(crate) fn rpc_rotate_host_token_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    role: &str,
    room: Option<&str>,
    expires_in_seconds: Option<u64>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RotateHostToken {
            role: role.to_string(),
            room: room.map(|value| value.to_string()),
            expires_in_seconds,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request token rotation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for token rotation response".to_string())?
}

pub(crate) fn rpc_revoke_host_token_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    value: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RevokeHostToken {
            value: value.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request token revocation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for token revocation response".to_string())?
}

pub(crate) fn rpc_handoff_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::HandoffHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request role handoff: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for role handoff response".to_string())?
}

pub(crate) fn rpc_set_host_preset_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    preset: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHostPreset {
            preset: preset.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request preset update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for preset update response".to_string())?
}

pub(crate) fn rpc_list_host_activity_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
    limit: u64,
    event_type: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListHostActivity {
            room: room.map(|value| value.to_string()),
            limit,
            event_type: event_type.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host activity: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host activity response".to_string())?
}

pub(crate) fn rpc_start_service_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
    command: Option<&str>,
    cwd: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StartService {
            name: name.to_string(),
            command: command.map(|value| value.to_string()),
            cwd: cwd.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service start: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(90))
        .map_err(|_| "Timed out waiting for service start response".to_string())?
}

pub(crate) fn rpc_stop_service_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StopService {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service stop: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for service stop response".to_string())?
}

pub(crate) fn rpc_get_service_status_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetServiceStatus {
            name: name.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for service status response".to_string())?
}

pub(crate) fn rpc_get_service_logs_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
    lines: Option<u64>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetServiceLogs {
            name: name.to_string(),
            lines,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service logs: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for service logs response".to_string())?
}

pub(crate) fn rpc_pair_start_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    lobby: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::PairStart {
            lobby,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request pair start: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for pair start response".to_string())?
}

pub(crate) fn rpc_suggest_text_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    text: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SuggestText {
            text: text.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send suggestion: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for suggest response".to_string())?
}

pub(crate) fn rpc_add_agenda_item_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    text: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::AddAgendaItem {
            text: text.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to add agenda item: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for agenda add response".to_string())?
}

pub(crate) fn rpc_list_agenda_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
    include_resolved: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListAgenda {
            room: room.map(|value| value.to_string()),
            include_resolved,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to list agenda: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for agenda list response".to_string())?
}

pub(crate) fn rpc_resolve_agenda_item_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    item_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ResolveAgendaItem {
            item_id: item_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to resolve agenda item: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for agenda resolve response".to_string())?
}

pub(crate) fn rpc_set_hand_raised_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    raised: bool,
    room: Option<&str>,
    connection_id: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHandRaised {
            raised,
            room: room.map(|value| value.to_string()),
            connection_id: connection_id.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to update hand raise state: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for hand raise response".to_string())?
}

pub(crate) fn rpc_next_driver_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::NextDriver {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request next driver: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(15))
        .map_err(|_| "Timed out waiting for next driver response".to_string())?
}

pub(crate) fn rpc_pass_driver_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    display_name: Option<&str>,
    connection_id: Option<&str>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::PassDriver {
            display_name: display_name.map(|s| s.to_string()),
            connection_id: connection_id.map(|s| s.to_string()),
            room: room.map(|s| s.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request pass driver: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(15))
        .map_err(|_| "Timed out waiting for pass driver response".to_string())?
}

pub(crate) fn copy_to_clipboard(content: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        return copy_with_command("pbcopy", &[], content);
    }

    #[cfg(target_os = "windows")]
    {
        return copy_with_command("clip", &[], content);
    }

    #[cfg(target_os = "linux")]
    {
        for (bin, args) in [
            ("wl-copy", Vec::<&str>::new()),
            ("xclip", vec!["-selection", "clipboard"]),
            ("xsel", vec!["--clipboard", "--input"]),
        ] {
            if copy_with_command(bin, &args, content).is_ok() {
                return Ok(());
            }
        }
        return Err("No clipboard utility found. Install wl-copy, xclip, or xsel.".to_string());
    }

    #[allow(unreachable_code)]
    Err("Clipboard is not supported on this platform.".to_string())
}

pub(crate) fn copy_with_command(bin: &str, args: &[&str], content: &str) -> Result<(), String> {
    let mut child = Command::new(bin)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("Failed to run `{bin}`: {e}"))?;

    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write as _;
        stdin
            .write_all(content.as_bytes())
            .map_err(|e| format!("Failed writing to `{bin}` stdin: {e}"))?;
    }

    let status = child
        .wait()
        .map_err(|e| format!("Failed waiting for `{bin}`: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("`{bin}` exited with status {status}"))
    }
}
