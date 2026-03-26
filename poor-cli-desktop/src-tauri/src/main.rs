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
            commands::create_session,
            commands::destroy_session,
            commands::get_status_view,
            commands::list_providers,
            commands::rename_session,
            commands::get_config,
            commands::set_config,
            commands::list_config_options,
            commands::get_api_key_status,
            commands::list_skills,
            commands::list_automations,
            commands::preview_mutation,
            commands::save_session,
            commands::restore_session,
            commands::list_history,
            commands::search_history,
            commands::get_session_cost,
        ])
        .run(tauri::generate_context!())
        .expect("error running poor-cli desktop");
}
