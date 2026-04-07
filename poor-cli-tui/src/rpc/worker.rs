use std::sync::mpsc::Receiver;
use std::sync::Arc;
use std::thread;
use super::{RpcClient, RpcCommand};

/// Blocks the calling thread, dispatching RPC commands until Shutdown or channel drop.
/// Chat and ChatStreaming are dispatched to background threads so the worker
/// remains responsive to other commands (e.g. /switch, /config) during streaming.
pub fn run_rpc_worker(client: RpcClient, rx: Receiver<RpcCommand>) {
    let client = Arc::new(client);
    loop {
        match rx.recv() {
            Ok(RpcCommand::Chat {
                message,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let c = Arc::clone(&client);
                thread::spawn(move || {
                    let result = c
                        .chat(
                            &message,
                            &context_files,
                            &pinned_context_files,
                            context_budget_tokens,
                        )
                        .map(|r| r.content.unwrap_or_default());
                    let _ = reply.send(result);
                });
            }
            Ok(RpcCommand::ChatStreaming {
                message,
                request_id,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let c = Arc::clone(&client);
                thread::spawn(move || {
                    let result = c
                        .chat_streaming(
                            &message,
                            &request_id,
                            &context_files,
                            &pinned_context_files,
                            context_budget_tokens,
                        )
                        .map(|r| r.content.unwrap_or_default());
                    let _ = reply.send(result);
                });
            }
            Ok(RpcCommand::PreviewContext {
                message,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let _ = reply.send(client.preview_context(
                    &message,
                    &context_files,
                    &pinned_context_files,
                    context_budget_tokens,
                ));
            }
            Ok(RpcCommand::PreviewMutation {
                tool_name,
                tool_args,
                reply,
            }) => {
                let _ = reply.send(client.preview_mutation(&tool_name, tool_args));
            }
            Ok(RpcCommand::CancelRequest) => {
                let _ = client.cancel_request();
            }
            Ok(RpcCommand::SendNotification { method, params }) => {
                let _ = client.send_notification(&method, params);
            }
            Ok(RpcCommand::ExecuteCommand {
                command,
                timeout,
                reply,
            }) => {
                let _ = reply.send(client.execute_command(&command, timeout));
            }
            Ok(RpcCommand::ReadFile {
                file_path,
                start_line,
                end_line,
                reply,
            }) => {
                let _ = reply.send(client.read_file(&file_path, start_line, end_line));
            }
            Ok(RpcCommand::GetConfig { reply }) => {
                let _ = reply.send(client.get_config_value());
            }
            Ok(RpcCommand::GetPermissions { reply }) => {
                let _ = reply.send(client.get_permissions());
            }
            Ok(RpcCommand::SetPermissions {
                mode,
                add_rule,
                clear_session_rules,
                reply,
            }) => {
                let _ = reply.send(client.set_permissions(
                    mode.as_deref(),
                    add_rule,
                    clear_session_rules,
                ));
            }
            Ok(RpcCommand::GetProviderInfo { reply }) => {
                let _ = reply.send(client.get_provider_info());
            }
            Ok(RpcCommand::GetTools { reply }) => {
                let _ = reply.send(client.get_tools());
            }
            Ok(RpcCommand::GetInstructionStack {
                referenced_files,
                reply,
            }) => {
                let _ = reply.send(client.get_instruction_stack(&referenced_files));
            }
            Ok(RpcCommand::GetStatusView { reply }) => {
                let _ = reply.send(client.get_status_view());
            }
            Ok(RpcCommand::GetTrustView { reply }) => {
                let _ = reply.send(client.get_trust_view());
            }
            Ok(RpcCommand::GetDoctorReport { reply }) => {
                let _ = reply.send(client.get_doctor_report());
            }
            Ok(RpcCommand::GetPolicyStatus { reply }) => {
                let _ = reply.send(client.get_policy_status());
            }
            Ok(RpcCommand::GetSandboxStatus { reply }) => {
                let _ = reply.send(client.get_sandbox_status());
            }
            Ok(RpcCommand::GetMcpStatus { reply }) => {
                let _ = reply.send(client.get_mcp_status());
            }
            Ok(RpcCommand::GcCheckpoints { reply }) => {
                let _ = reply.send(client.gc_checkpoints());
            }
            Ok(RpcCommand::McpHealthCheck { reply }) => {
                let _ = reply.send(client.mcp_health_check());
            }
            Ok(RpcCommand::ListOllamaModels { reply }) => {
                let _ = reply.send(client.list_ollama_models());
            }
            Ok(RpcCommand::SaveSession { reply }) => {
                let _ = reply.send(client.save_session());
            }
            Ok(RpcCommand::RestoreSession { session_id, reply }) => {
                let _ = reply.send(client.restore_session(session_id.as_deref()));
            }
            Ok(RpcCommand::GetEconomySavings { reply }) => {
                let _ = reply.send(client.get_economy_savings());
            }
            Ok(RpcCommand::SetEconomyPreset { preset, reply }) => {
                let _ = reply.send(client.set_economy_preset(&preset));
            }
            Ok(RpcCommand::GetContextExplain {
                message,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let _ = reply.send(client.get_context_explain(
                    &message,
                    &context_files,
                    &pinned_context_files,
                    context_budget_tokens,
                ));
            }
            Ok(RpcCommand::ListRuns {
                source_kind,
                source_id,
                limit,
                reply,
            }) => {
                let _ = reply.send(client.list_runs(
                    source_kind.as_deref(),
                    source_id.as_deref(),
                    limit,
                ));
            }
            Ok(RpcCommand::ListWorkflows { reply }) => {
                let _ = reply.send(client.list_workflows());
            }
            Ok(RpcCommand::GetWorkflow { name, reply }) => {
                let _ = reply.send(client.get_workflow(&name));
            }
            Ok(RpcCommand::ListSkills { reply }) => {
                let _ = reply.send(client.list_skills());
            }
            Ok(RpcCommand::GetSkill { name, reply }) => {
                let _ = reply.send(client.get_skill(&name));
            }
            Ok(RpcCommand::ListCustomCommands { reply }) => {
                let _ = reply.send(client.list_custom_commands());
            }
            Ok(RpcCommand::GetCustomCommand { name, reply }) => {
                let _ = reply.send(client.get_custom_command(&name));
            }
            Ok(RpcCommand::RunCustomCommand {
                name,
                args_text,
                reply,
            }) => {
                let _ = reply.send(client.run_custom_command(&name, &args_text));
            }
            Ok(RpcCommand::ListConfigOptions { reply }) => {
                let _ = reply.send(client.list_config_options());
            }
            Ok(RpcCommand::SetConfig {
                key_path,
                value,
                reply,
            }) => {
                let _ = reply.send(client.set_config(&key_path, value));
            }
            Ok(RpcCommand::ToggleConfig { key_path, reply }) => {
                let _ = reply.send(client.toggle_config(&key_path));
            }
            Ok(RpcCommand::Initialize {
                provider,
                model,
                permission_mode,
                reply,
            }) => {
                let _ = reply.send(client.initialize(
                    provider.as_deref(),
                    model.as_deref(),
                    None,
                    permission_mode.as_deref(),
                ));
            }
            Ok(RpcCommand::SetApiKey {
                provider,
                api_key,
                persist,
                reply,
            }) => {
                let _ = reply.send(client.set_api_key(&provider, &api_key, persist));
            }
            Ok(RpcCommand::GetApiKeyStatus { provider, reply }) => {
                let _ = reply.send(client.get_api_key_status(provider.as_deref()));
            }
            Ok(RpcCommand::ClearHistory { reply }) => {
                let _ = reply.send(client.clear_history());
            }
            Ok(RpcCommand::CompactContext { strategy, reply }) => {
                let _ = reply.send(client.compact_context(&strategy));
            }
            Ok(RpcCommand::ListSessions { limit, reply }) => {
                let _ = reply.send(client.list_sessions(limit));
            }
            Ok(RpcCommand::ListHistory { count, reply }) => {
                let _ = reply.send(client.list_history(count));
            }
            Ok(RpcCommand::SearchHistory { term, reply }) => {
                let _ = reply.send(client.search_history(&term));
            }
            Ok(RpcCommand::CreateTask {
                title,
                prompt,
                sandbox_preset,
                source,
                auto_start,
                requires_approval,
                reply,
            }) => {
                let _ = reply.send(client.create_task(
                    &title,
                    &prompt,
                    &sandbox_preset,
                    &source,
                    auto_start,
                    requires_approval,
                ));
            }
            Ok(RpcCommand::ListTasks { inbox_only, reply }) => {
                let _ = reply.send(client.list_tasks(inbox_only));
            }
            Ok(RpcCommand::GetTask { task_id, reply }) => {
                let _ = reply.send(client.get_task(&task_id));
            }
            Ok(RpcCommand::ApproveTask { task_id, reply }) => {
                let _ = reply.send(client.approve_task(&task_id));
            }
            Ok(RpcCommand::CancelTask { task_id, reply }) => {
                let _ = reply.send(client.cancel_task(&task_id));
            }
            Ok(RpcCommand::RetryTask { task_id, reply }) => {
                let _ = reply.send(client.retry_task(&task_id));
            }
            Ok(RpcCommand::ReplayTask { task_id, reply }) => {
                let _ = reply.send(client.replay_task(&task_id));
            }
            Ok(RpcCommand::ListAutomations {
                enabled,
                limit,
                reply,
            }) => {
                let _ = reply.send(client.list_automations(enabled, limit));
            }
            Ok(RpcCommand::GetAutomationHistory {
                automation_id,
                limit,
                reply,
            }) => {
                let _ = reply.send(client.get_automation_history(&automation_id, limit));
            }
            Ok(RpcCommand::ReplayAutomation {
                automation_id,
                reply,
            }) => {
                let _ = reply.send(client.replay_automation(&automation_id));
            }
            Ok(RpcCommand::ListCheckpoints { limit, reply }) => {
                let _ = reply.send(client.list_checkpoints(limit));
            }
            Ok(RpcCommand::CreateCheckpoint {
                description,
                operation_type,
                reply,
            }) => {
                let _ = reply.send(client.create_checkpoint(&description, &operation_type));
            }
            Ok(RpcCommand::RestoreCheckpoint {
                checkpoint_id,
                reply,
            }) => {
                let _ = reply.send(client.restore_checkpoint(checkpoint_id.as_deref()));
            }
            Ok(RpcCommand::PreviewCheckpoint {
                checkpoint_id,
                reply,
            }) => {
                let _ = reply.send(client.preview_checkpoint(&checkpoint_id));
            }
            Ok(RpcCommand::CompareFiles {
                file1,
                file2,
                reply,
            }) => {
                let _ = reply.send(client.compare_files(&file1, &file2));
            }
            Ok(RpcCommand::ExportConversation { format, reply }) => {
                let _ = reply.send(client.export_conversation(&format));
            }
            Ok(RpcCommand::StartHostServer { room, reply }) => {
                let _ = reply.send(client.start_host_server(room.as_deref()));
            }
            Ok(RpcCommand::GetHostServerStatus { reply }) => {
                let _ = reply.send(client.get_host_server_status());
            }
            Ok(RpcCommand::GetCollabSummary { reply }) => {
                let _ = reply.send(client.get_collab_summary());
            }
            Ok(RpcCommand::StopHostServer { reply }) => {
                let _ = reply.send(client.stop_host_server());
            }
            Ok(RpcCommand::ListHostMembers { room, reply }) => {
                let _ = reply.send(client.list_host_members(room.as_deref()));
            }
            Ok(RpcCommand::ListRoomMembers { room, reply }) => {
                let _ = reply.send(client.list_room_members(room.as_deref()));
            }
            Ok(RpcCommand::RemoveHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.remove_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::KickMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.kick_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::SetHostMemberRole {
                connection_id,
                role,
                room,
                reply,
            }) => {
                let _ =
                    reply.send(client.set_host_member_role(&connection_id, &role, room.as_deref()));
            }
            Ok(RpcCommand::SetHostLobby {
                enabled,
                room,
                reply,
            }) => {
                let _ = reply.send(client.set_host_lobby(enabled, room.as_deref()));
            }
            Ok(RpcCommand::ApproveHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.approve_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::DenyHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.deny_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::RotateHostToken {
                role,
                room,
                expires_in_seconds,
                reply,
            }) => {
                let _ = reply.send(client.rotate_host_token(
                    &role,
                    room.as_deref(),
                    expires_in_seconds,
                ));
            }
            Ok(RpcCommand::RevokeHostToken { value, room, reply }) => {
                let _ = reply.send(client.revoke_host_token(&value, room.as_deref()));
            }
            Ok(RpcCommand::HandoffHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.handoff_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::SetHostPreset {
                preset,
                room,
                reply,
            }) => {
                let _ = reply.send(client.set_host_preset(&preset, room.as_deref()));
            }
            Ok(RpcCommand::ListHostActivity {
                room,
                limit,
                event_type,
                reply,
            }) => {
                let _ = reply.send(client.list_host_activity(
                    room.as_deref(),
                    limit,
                    event_type.as_deref(),
                ));
            }
            Ok(RpcCommand::StartService {
                name,
                command,
                cwd,
                reply,
            }) => {
                let _ = reply.send(client.start_service(&name, command.as_deref(), cwd.as_deref()));
            }
            Ok(RpcCommand::StopService { name, reply }) => {
                let _ = reply.send(client.stop_service(&name));
            }
            Ok(RpcCommand::GetServiceStatus { name, reply }) => {
                let _ = reply.send(client.get_service_status(name.as_deref()));
            }
            Ok(RpcCommand::GetServiceLogs { name, lines, reply }) => {
                let _ = reply.send(client.get_service_logs(&name, lines));
            }
            Ok(RpcCommand::ListProviders { reply }) => {
                let _ = reply.send(client.list_providers());
            }
            Ok(RpcCommand::SwitchProvider {
                provider,
                model,
                reply,
            }) => {
                let p_clone = provider.clone();
                let m_clone = model.clone();
                let result = client
                    .switch_provider(&provider, model.as_deref())
                    .map(|val| {
                        let prov = val
                            .pointer("/provider/name")
                            .and_then(|v| v.as_str())
                            .unwrap_or(&p_clone)
                            .to_string();
                        let mdl = val
                            .pointer("/provider/model")
                            .and_then(|v| v.as_str())
                            .unwrap_or(m_clone.as_deref().unwrap_or("default"))
                            .to_string();
                        (prov, mdl)
                    });
                let _ = reply.send(result);
            }
            Ok(RpcCommand::PairStart { lobby, reply }) => {
                let _ = reply.send(client.pair_start(lobby));
            }
            Ok(RpcCommand::SuggestText { text, reply }) => {
                let _ = reply.send(client.suggest_text(&text));
            }
            Ok(RpcCommand::AddAgendaItem { text, room, reply }) => {
                let _ = reply.send(client.add_agenda_item(&text, room.as_deref()));
            }
            Ok(RpcCommand::ListAgenda {
                room,
                include_resolved,
                reply,
            }) => {
                let _ = reply.send(client.list_agenda(room.as_deref(), include_resolved));
            }
            Ok(RpcCommand::ResolveAgendaItem {
                item_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.resolve_agenda_item(&item_id, room.as_deref()));
            }
            Ok(RpcCommand::SetHandRaised {
                raised,
                room,
                connection_id,
                reply,
            }) => {
                let _ = reply.send(client.set_hand_raised(
                    raised,
                    room.as_deref(),
                    connection_id.as_deref(),
                ));
            }
            Ok(RpcCommand::NextDriver { room, reply }) => {
                let _ = reply.send(client.next_driver(room.as_deref()));
            }
            Ok(RpcCommand::PassDriver {
                display_name,
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.pass_driver(
                    display_name.as_deref(),
                    connection_id.as_deref(),
                    room.as_deref(),
                ));
            }
            // ── Group A: Agent Management ────────────────────────────
            Ok(RpcCommand::CreateAgent { prompt, sandbox_preset, auto_start, reply }) => {
                let _ = reply.send(client.create_agent(&prompt, &sandbox_preset, auto_start));
            }
            Ok(RpcCommand::ListAgents { statuses, reply }) => {
                let _ = reply.send(client.list_agents(statuses.as_deref()));
            }
            Ok(RpcCommand::GetAgent { agent_id, reply }) => {
                let _ = reply.send(client.get_agent(&agent_id));
            }
            Ok(RpcCommand::StartAgent { agent_id, reply }) => {
                let _ = reply.send(client.start_agent(&agent_id));
            }
            Ok(RpcCommand::CancelAgent { agent_id, reply }) => {
                let _ = reply.send(client.cancel_agent(&agent_id));
            }
            Ok(RpcCommand::GetAgentLogs { agent_id, tail, reply }) => {
                let _ = reply.send(client.get_agent_logs(&agent_id, tail));
            }
            Ok(RpcCommand::GetAgentResult { agent_id, reply }) => {
                let _ = reply.send(client.get_agent_result(&agent_id));
            }
            // ── Group B: Memory System ─────────────────────────────
            Ok(RpcCommand::MemoryList { type_filter, reply }) => {
                let _ = reply.send(client.memory_list(type_filter.as_deref()));
            }
            Ok(RpcCommand::MemorySave { name, type_, description, content, reply }) => {
                let _ = reply.send(client.memory_save(&name, &type_, &description, &content));
            }
            Ok(RpcCommand::MemorySearch { query, type_filter, max_results, reply }) => {
                let _ = reply.send(client.memory_search(&query, type_filter.as_deref(), max_results));
            }
            Ok(RpcCommand::MemoryDelete { name, reply }) => {
                let _ = reply.send(client.memory_delete(&name));
            }
            // ── Group C: Deploy Pipeline ───────────────────────────
            Ok(RpcCommand::Deploy { target, prod, reply }) => {
                let _ = reply.send(client.deploy(target.as_deref(), prod));
            }
            Ok(RpcCommand::DeployTargets { reply }) => {
                let _ = reply.send(client.deploy_targets());
            }
            Ok(RpcCommand::DeployValidate { reply }) => {
                let _ = reply.send(client.deploy_validate());
            }
            Ok(RpcCommand::DeployHistory { limit, reply }) => {
                let _ = reply.send(client.deploy_history(limit));
            }
            // ── Group D: Trust/Profile Management ──────────────────
            Ok(RpcCommand::ListProfiles { reply }) => {
                let _ = reply.send(client.list_profiles());
            }
            Ok(RpcCommand::ApplyProfile { name, reply }) => {
                let _ = reply.send(client.apply_profile(&name));
            }
            Ok(RpcCommand::GetTrustStatus { reply }) => {
                let _ = reply.send(client.get_trust_status());
            }
            Ok(RpcCommand::TrustRepo { path, reply }) => {
                let _ = reply.send(client.trust_repo(path.as_deref()));
            }
            Ok(RpcCommand::UntrustRepo { path, reply }) => {
                let _ = reply.send(client.untrust_repo(path.as_deref()));
            }
            // ── Group E: Preview/Watch ─────────────────────────────
            Ok(RpcCommand::PreviewStart { port, reply }) => {
                let _ = reply.send(client.preview_start(port));
            }
            Ok(RpcCommand::PreviewStop { reply }) => {
                let _ = reply.send(client.preview_stop());
            }
            Ok(RpcCommand::PreviewStatus { reply }) => {
                let _ = reply.send(client.preview_status());
            }
            Ok(RpcCommand::WatchScan { root, reply }) => {
                let _ = reply.send(client.watch_scan(root.as_deref()));
            }
            // ── Group F: Docker Sandbox Status ─────────────────────
            Ok(RpcCommand::GetDockerSandboxStatus { reply }) => {
                let _ = reply.send(client.get_docker_sandbox_status());
            }
            // ── Group G: Search/Indexing ───────────────────────────
            Ok(RpcCommand::SemanticSearch { query, max_results, file_filter, reply }) => {
                let _ = reply.send(client.semantic_search(&query, max_results, file_filter.as_deref()));
            }
            Ok(RpcCommand::IndexCodebase { force, reply }) => {
                let _ = reply.send(client.index_codebase(force));
            }
            Ok(RpcCommand::GetIndexStats { reply }) => {
                let _ = reply.send(client.get_index_stats());
            }
            Ok(RpcCommand::IndexEmbeddings { provider, force, reply }) => {
                let _ = reply.send(client.index_embeddings(provider.as_deref(), force));
            }
            Ok(RpcCommand::VectorSearch { query, max_results, file_filter, reply }) => {
                let _ = reply.send(client.vector_search(&query, max_results, file_filter.as_deref()));
            }
            Ok(RpcCommand::HybridSearch { query, max_results, file_filter, reply }) => {
                let _ = reply.send(client.hybrid_search(&query, max_results, file_filter.as_deref()));
            }
            Ok(RpcCommand::Shutdown) | Err(_) => break,
        }
    }
}
