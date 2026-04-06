use serde_json::Value;
use std::sync::mpsc::SyncSender;
use super::{InitResult, ProviderInfo};

pub enum RpcCommand {
    Chat {
        message: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<String, String>>,
    },
    ChatStreaming {
        message: String,
        request_id: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<String, String>>,
    },
    PreviewContext {
        message: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<Value, String>>,
    },
    PreviewMutation {
        tool_name: String,
        tool_args: Value,
        reply: SyncSender<Result<Value, String>>,
    },
    CancelRequest,
    SendNotification {
        method: String,
        params: Value,
    },
    ExecuteCommand {
        command: String,
        timeout: Option<u64>,
        reply: SyncSender<Result<String, String>>,
    },
    ReadFile {
        file_path: String,
        start_line: Option<u64>,
        end_line: Option<u64>,
        reply: SyncSender<Result<String, String>>,
    },
    GetConfig {
        reply: SyncSender<Result<Value, String>>,
    },
    GetPermissions {
        reply: SyncSender<Result<Value, String>>,
    },
    SetPermissions {
        mode: Option<String>,
        add_rule: Option<Value>,
        clear_session_rules: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    GetProviderInfo {
        reply: SyncSender<Result<Value, String>>,
    },
    GetTools {
        reply: SyncSender<Result<Value, String>>,
    },
    GetInstructionStack {
        referenced_files: Vec<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    GetStatusView {
        reply: SyncSender<Result<Value, String>>,
    },
    GetTrustView {
        reply: SyncSender<Result<Value, String>>,
    },
    GetDoctorReport {
        reply: SyncSender<Result<Value, String>>,
    },
    GetPolicyStatus {
        reply: SyncSender<Result<Value, String>>,
    },
    GetSandboxStatus {
        reply: SyncSender<Result<Value, String>>,
    },
    GetMcpStatus {
        reply: SyncSender<Result<Value, String>>,
    },
    GcCheckpoints {
        reply: SyncSender<Result<Value, String>>,
    },
    McpHealthCheck {
        reply: SyncSender<Result<Value, String>>,
    },
    ListOllamaModels {
        reply: SyncSender<Result<Value, String>>,
    },
    SaveSession {
        reply: SyncSender<Result<Value, String>>,
    },
    RestoreSession {
        session_id: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    GetEconomySavings {
        reply: SyncSender<Result<Value, String>>,
    },
    SetEconomyPreset {
        preset: String,
        reply: SyncSender<Result<Value, String>>,
    },
    GetContextExplain {
        message: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListRuns {
        source_kind: Option<String>,
        source_id: Option<String>,
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    ListWorkflows {
        reply: SyncSender<Result<Value, String>>,
    },
    GetWorkflow {
        name: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListSkills {
        reply: SyncSender<Result<Value, String>>,
    },
    GetSkill {
        name: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListCustomCommands {
        reply: SyncSender<Result<Value, String>>,
    },
    GetCustomCommand {
        name: String,
        reply: SyncSender<Result<Value, String>>,
    },
    RunCustomCommand {
        name: String,
        args_text: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListConfigOptions {
        reply: SyncSender<Result<Value, String>>,
    },
    SetConfig {
        key_path: String,
        value: Value,
        reply: SyncSender<Result<Value, String>>,
    },
    ToggleConfig {
        key_path: String,
        reply: SyncSender<Result<Value, String>>,
    },
    Initialize {
        provider: Option<String>,
        model: Option<String>,
        permission_mode: Option<String>,
        reply: SyncSender<Result<InitResult, String>>,
    },
    SetApiKey {
        provider: String,
        api_key: String,
        persist: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    GetApiKeyStatus {
        provider: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ClearHistory {
        reply: SyncSender<Result<(), String>>,
    },
    CompactContext {
        strategy: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListSessions {
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    ListHistory {
        count: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    SearchHistory {
        term: String,
        reply: SyncSender<Result<Value, String>>,
    },
    CreateTask {
        title: String,
        prompt: String,
        sandbox_preset: String,
        source: String,
        auto_start: bool,
        requires_approval: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    ListTasks {
        inbox_only: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    GetTask {
        task_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ApproveTask {
        task_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    CancelTask {
        task_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    RetryTask {
        task_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ReplayTask {
        task_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListAutomations {
        enabled: Option<bool>,
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    GetAutomationHistory {
        automation_id: String,
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    ReplayAutomation {
        automation_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListCheckpoints {
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    CreateCheckpoint {
        description: String,
        operation_type: String,
        reply: SyncSender<Result<Value, String>>,
    },
    RestoreCheckpoint {
        checkpoint_id: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    PreviewCheckpoint {
        checkpoint_id: String,
        reply: SyncSender<Result<Value, String>>,
    },
    CompareFiles {
        file1: String,
        file2: String,
        reply: SyncSender<Result<String, String>>,
    },
    ExportConversation {
        format: String,
        reply: SyncSender<Result<Value, String>>,
    },
    StartHostServer {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    GetHostServerStatus {
        reply: SyncSender<Result<Value, String>>,
    },
    GetCollabSummary {
        reply: SyncSender<Result<Value, String>>,
    },
    StopHostServer {
        reply: SyncSender<Result<Value, String>>,
    },
    ListHostMembers {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListRoomMembers {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    RemoveHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    KickMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHostMemberRole {
        connection_id: String,
        role: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHostLobby {
        enabled: bool,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ApproveHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    DenyHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    RotateHostToken {
        role: String,
        room: Option<String>,
        expires_in_seconds: Option<u64>,
        reply: SyncSender<Result<Value, String>>,
    },
    RevokeHostToken {
        value: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    HandoffHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHostPreset {
        preset: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListHostActivity {
        room: Option<String>,
        limit: u64,
        event_type: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    StartService {
        name: String,
        command: Option<String>,
        cwd: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    StopService {
        name: String,
        reply: SyncSender<Result<Value, String>>,
    },
    GetServiceStatus {
        name: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    GetServiceLogs {
        name: String,
        lines: Option<u64>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListProviders {
        reply: SyncSender<Result<Vec<ProviderInfo>, String>>,
    },
    SwitchProvider {
        provider: String,
        model: Option<String>,
        reply: SyncSender<Result<(String, String), String>>,
    },
    PairStart {
        lobby: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    SuggestText {
        text: String,
        reply: SyncSender<Result<Value, String>>,
    },
    AddAgendaItem {
        text: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListAgenda {
        room: Option<String>,
        include_resolved: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    ResolveAgendaItem {
        item_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHandRaised {
        raised: bool,
        room: Option<String>,
        connection_id: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    NextDriver {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    PassDriver {
        display_name: Option<String>,
        connection_id: Option<String>,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    Shutdown,
}
