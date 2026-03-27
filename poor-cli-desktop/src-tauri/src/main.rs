// poor-cli desktop app — Tauri v2 entry point
// spawns poor-cli-server as a sidecar and communicates via JSON-RPC over stdio.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod state;

use state::AppState;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            commands::send_chat,
            commands::initialize_backend,
            commands::get_provider_info,
            commands::switch_provider,
            commands::clear_history,
            commands::list_sessions,
            commands::switch_session,
            commands::create_session,
            commands::destroy_session,
            commands::get_status_view,
            commands::list_providers,
            commands::rename_session,
            commands::get_config,
            commands::set_config,
            commands::list_config_options,
            commands::get_api_key_status,
            commands::set_api_key,
            commands::list_skills,
            commands::list_automations,
            commands::preview_mutation,
            commands::save_session,
            commands::restore_session,
            commands::list_history,
            commands::search_history,
            commands::get_session_cost,
            commands::search_workspace_files,
            // multiplayer
            commands::start_host_server,
            commands::stop_host_server,
            commands::get_host_server_status,
            commands::pair_start,
            commands::join_remote_session,
            commands::leave_remote_session,
            commands::rotate_host_token,
            commands::revoke_host_token,
            commands::list_host_members,
            commands::remove_host_member,
            commands::set_host_member_role,
            commands::set_host_lobby,
            commands::approve_host_member,
            commands::deny_host_member,
            commands::handoff_host_member,
            commands::next_driver,
            commands::pass_driver,
            commands::set_host_preset,
            commands::list_host_activity,
            commands::suggest_text,
            commands::set_hand_raised,
            commands::add_agenda_item,
            commands::list_agenda,
            commands::resolve_agenda_item,
            // tasks
            commands::create_task,
            commands::list_tasks,
            commands::get_task,
            commands::start_task,
            commands::approve_task,
            commands::cancel_task,
            commands::retry_task,
            commands::replay_task,
            // checkpoints
            commands::list_checkpoints,
            commands::create_checkpoint,
            commands::restore_checkpoint,
            commands::preview_checkpoint,
            // automation CRUD
            commands::create_automation,
            commands::get_automation,
            commands::set_automation_enabled,
            commands::run_automation_now,
            commands::get_automation_history,
            commands::replay_automation,
            // custom commands
            commands::list_custom_commands,
            commands::get_custom_command,
            commands::run_custom_command,
            // workflows
            commands::list_workflows,
            commands::get_workflow,
            // tools & MCP
            commands::get_tools,
            commands::get_mcp_status,
            // diagnostics
            commands::get_doctor_report,
            commands::get_policy_status,
            commands::get_trust_view,
            commands::get_sandbox_status,
            // export
            commands::export_conversation,
            // services
            commands::start_service,
            commands::stop_service,
            commands::get_service_status,
            commands::get_service_logs,
        ])
        .run(tauri::generate_context!())
        .expect("error running poor-cli desktop");
}
