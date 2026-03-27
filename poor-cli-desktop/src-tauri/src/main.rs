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
        ])
        .run(tauri::generate_context!())
        .expect("error running poor-cli desktop");
}
