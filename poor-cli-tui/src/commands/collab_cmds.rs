use super::super::*;
use super::collab::{collab_share_role, collab_usage_text, current_multiplayer_room, first_host_room_name, room_field};
use super::core::show_command_info_popup;

/// Recursive dispatch helper -- calls back into the top-level handler.
fn dispatch(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
    cmd: &str,
) -> bool {
    super::handle_slash_command(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, cmd)
}

pub(super) fn handle_collab_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    // ── Collaboration commands ────────────────────────────────────────
    if lowered == "/collab" || lowered.starts_with("/collab ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("help")
            .trim()
            .to_ascii_lowercase();

        if args.len() == 1 || subcommand.is_empty() || subcommand == "help" {
            let hosting = app.pair.mode_active && app.pair.is_host;
            let guest = app.multiplayer.enabled && !app.pair.is_host;
            let (title, items) = if hosting {
                ("Collaboration (Hosting)", vec![
                    ListSelectorItem { label: "status: Show session status".into(), value: "status".into() },
                    ListSelectorItem { label: "members: List session members".into(), value: "members".into() },
                    ListSelectorItem { label: "share: Share invite code".into(), value: "share".into() },
                    ListSelectorItem { label: "handoff: Hand off driver role".into(), value: "handoff".into() },
                    ListSelectorItem { label: "agenda: View agenda".into(), value: "agenda list".into() },
                    ListSelectorItem { label: "lobby: Lobby settings".into(), value: "lobby".into() },
                    ListSelectorItem { label: "leave: End session".into(), value: "leave".into() },
                ])
            } else if guest {
                ("Collaboration (Guest)", vec![
                    ListSelectorItem { label: "status: Show session status".into(), value: "status".into() },
                    ListSelectorItem { label: "members: List session members".into(), value: "members".into() },
                    ListSelectorItem { label: "suggest: Send suggestion to driver".into(), value: "suggest".into() },
                    ListSelectorItem { label: "hand raise: Raise your hand".into(), value: "hand raise".into() },
                    ListSelectorItem { label: "agenda: View agenda".into(), value: "agenda list".into() },
                    ListSelectorItem { label: "leave: Leave session".into(), value: "leave".into() },
                ])
            } else {
                ("Collaboration", vec![
                    ListSelectorItem { label: "start pair: Start pair programming".into(), value: "start pair".into() },
                    ListSelectorItem { label: "start mob: Start mob session".into(), value: "start mob".into() },
                    ListSelectorItem { label: "start review: Start code review".into(), value: "start review".into() },
                    ListSelectorItem { label: "join: Join a session".into(), value: "join".into() },
                ])
            };
            app.open_list_selector(ListSelectorState {
                title: title.into(), items, selected_idx: 0,
                command_template: "/collab {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }

        match subcommand.as_str() {
            "start" => {
                if args.len() != 3 {
                    show_command_info_popup(app, raw, collab_usage_text().to_string());
                    return Some(false);
                }

                let mode = args[2].trim().to_ascii_lowercase();
                match mode.as_str() {
                    "pair" => {
                        return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/pair start"));
                    }
                    "mob" | "review" => {
                        let start_payload = match rpc_start_host_server_blocking(rpc_cmd_tx, None) {
                            Ok(payload) => payload,
                            Err(e) => {
                                app.push_message(ChatMessage::error(format!(
                                    "Failed to start collaboration host: {e}"
                                )));
                                return Some(false);
                            }
                        };
                        let room_name =
                            first_host_room_name(&start_payload, current_multiplayer_room(app))
                                .unwrap_or_else(|| "dev".to_string());
                        let preset_payload = match rpc_set_host_preset_blocking(
                            rpc_cmd_tx,
                            &mode,
                            Some(room_name.as_str()),
                        ) {
                            Ok(payload) => payload,
                            Err(e) => {
                                app.push_message(ChatMessage::error(format!(
                                    "Started host, but failed to apply `{mode}` preset: {e}"
                                )));
                                return Some(false);
                            }
                        };
                        let host_payload = match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                            Ok(payload) => payload,
                            Err(_) => start_payload,
                        };

                        app.pair.is_host = true;
                        app.pair.mode_active = false;
                        app.multiplayer.enabled = true;
                        app.multiplayer.room = room_name.clone();
                        app.multiplayer.role = "prompter".to_string();
                        app.multiplayer.ui_role = "driver".to_string();
                        app.multiplayer.mode = mode.clone();
                        app.multiplayer.preset = mode.clone();
                        app.multiplayer.lobby_enabled = preset_payload
                            .get("lobbyEnabled")
                            .and_then(|value| value.as_bool())
                            .unwrap_or(mode != "pair");

                        let viewer_invite =
                            room_field(&host_payload, &room_name, "viewerInviteCode").unwrap_or("");
                        if !viewer_invite.is_empty() {
                            let _ = copy_to_clipboard(viewer_invite);
                        }

                        let mut lines = vec![format!("Started **{mode}** room `{room_name}`.")];
                        if !viewer_invite.is_empty() {
                            lines.push(
                                "Viewer invite code copied to clipboard. Use `/collab share driver` if you need a driver invite."
                                    .to_string(),
                            );
                        }
                        lines.push(String::new());
                        lines.push(format_host_share_payload(
                            &host_payload,
                            Some("viewer"),
                            Some(room_name.as_str()),
                        ));
                        lines.push(String::new());
                        lines.push("**Next steps:**".to_string());
                        lines.push("- Share the viewer invite with participants".to_string());
                        lines.push("- Use `/collab members` to check who joined".to_string());
                        lines.push("- Use `/collab handoff` to rotate driver".to_string());
                        lines.push("- Type `/collab` to see all session actions".to_string());
                        show_command_info_popup(app, raw, lines.join("\n"));
                        app.set_status(format!("{mode} room ready: {room_name}"));
                        return Some(false);
                    }
                    _ => {
                        show_command_info_popup(
                            app,
                            raw,
                            "Usage: /collab start <pair|mob|review>".to_string(),
                        );
                        return Some(false);
                    }
                }
            }
            "join" => {
                if args.len() == 3 {
                    let join_command = format!("/join-server {}", args[2]);
                    return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, &join_command));
                }
                if args.len() > 3 {
                    show_command_info_popup(
                        app,
                        raw,
                        "Usage: /collab join\n       /collab join <invite-code>".to_string(),
                    );
                    return Some(false);
                }
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/join-server"));
            }
            "status" => {
                if let Some(room) = current_multiplayer_room(app) {
                    match rpc_list_room_members_blocking(rpc_cmd_tx, Some(room)) {
                        Ok(payload) => {
                            let mut sections = vec![format_room_members_payload(&payload)];
                            if let Ok(agenda_payload) =
                                rpc_list_agenda_blocking(rpc_cmd_tx, Some(room), true)
                            {
                                sections.push(String::new());
                                sections.push(format_agenda_payload(&agenda_payload));
                            }
                            show_command_info_popup(app, raw, sections.join("\n"));
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to fetch collaboration status: {e}"
                        ))),
                    }
                } else {
                    match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                        Ok(payload) => {
                            show_command_info_popup(app, raw, format_host_server_payload(&payload))
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to fetch collaboration status: {e}"
                        ))),
                    }
                }
                return Some(false);
            }
            "summary" => {
                match rpc_get_collab_summary_blocking(rpc_cmd_tx) {
                    Ok(payload) => {
                        show_command_info_popup(app, raw, super::collab::format_collab_summary_payload(&payload))
                    }
                    Err(error) => show_command_info_popup(
                        app,
                        raw,
                        format!("Failed to load collaboration summary: {error}"),
                    ),
                }
                return Some(false);
            }
            "members" => {
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/members"));
            }
            "share" => {
                if args.len() > 3 {
                    show_command_info_popup(app, raw, collab_usage_text().to_string());
                    return Some(false);
                }
                let role_filter = if let Some(value) = args.get(2).copied() {
                    match collab_share_role(value) {
                        Some(role) => Some(role),
                        None => {
                            show_command_info_popup(
                                app,
                                raw,
                                "Usage: /collab share [driver|viewer]".to_string(),
                            );
                            return Some(false);
                        }
                    }
                } else {
                    None
                };
                match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                    Ok(payload) => show_command_info_popup(
                        app,
                        raw,
                        format_host_share_payload(
                            &payload,
                            role_filter,
                            current_multiplayer_room(app),
                        ),
                    ),
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to fetch share details: {e}"
                    ))),
                }
                return Some(false);
            }
            "handoff" => {
                if args.len() == 2 || (args.len() == 3 && args[2].eq_ignore_ascii_case("next")) {
                    match rpc_next_driver_blocking(rpc_cmd_tx, current_multiplayer_room(app)) {
                        Ok(payload) => {
                            let connection_id = payload
                                .get("connectionId")
                                .and_then(|value| value.as_str())
                                .unwrap_or("next driver");
                            app.set_status(format!("Driver handed off to `{connection_id}`"));
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to hand off driver: {e}"
                        ))),
                    }
                    return Some(false);
                }

                let target = args[2..].join(" ");
                let handoff_command = format!("/pass {target}");
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, &handoff_command));
            }
            "remove" => {
                if args.len() < 3 {
                    show_command_info_popup(
                        app,
                        raw,
                        "Usage: /collab remove [#N|@name|connection-id]".to_string(),
                    );
                    return Some(false);
                }
                let remove_command = format!("/kick {}", args[2..].join(" "));
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, &remove_command));
            }
            "lobby" => {
                if args.len() != 3 {
                    show_command_info_popup(app, raw, "Usage: /collab lobby <on|off>".to_string());
                    return Some(false);
                }
                let lobby_command = format!("/host-server lobby {}", args[2]);
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, &lobby_command));
            }
            "approve" | "deny" => {
                if args.len() < 3 {
                    show_command_info_popup(
                        app,
                        raw,
                        format!("Usage: /collab {subcommand} [#N|@name|connection-id]"),
                    );
                    return Some(false);
                }
                let review_command = format!("/host-server {subcommand} {}", args[2..].join(" "));
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, &review_command));
            }
            "agenda" => {
                let action = args
                    .get(2)
                    .copied()
                    .unwrap_or("")
                    .trim()
                    .to_ascii_lowercase();
                match action.as_str() {
                    "add" => {
                        let text = raw.splitn(4, ' ').nth(3).map(str::trim).unwrap_or("");
                        if text.is_empty() {
                            show_command_info_popup(
                                app,
                                raw,
                                "Usage: /collab agenda add <text>".to_string(),
                            );
                            return Some(false);
                        }
                        match rpc_add_agenda_item_blocking(
                            rpc_cmd_tx,
                            text,
                            current_multiplayer_room(app),
                        ) {
                            Ok(payload) => {
                                show_command_info_popup(app, raw, format_agenda_payload(&payload));
                                app.set_status("Agenda item added");
                            }
                            Err(e) => app.push_message(ChatMessage::error(format!(
                                "Failed to add agenda item: {e}"
                            ))),
                        }
                    }
                    "list" => match rpc_list_agenda_blocking(
                        rpc_cmd_tx,
                        current_multiplayer_room(app),
                        true,
                    ) {
                        Ok(payload) => show_command_info_popup(app, raw, format_agenda_payload(&payload)),
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to load agenda: {e}"
                        ))),
                    },
                    "done" => {
                        let item_id = args.get(3).copied().unwrap_or("").trim();
                        if item_id.is_empty() {
                            show_command_info_popup(
                                app,
                                raw,
                                "Usage: /collab agenda done <item-id>".to_string(),
                            );
                            return Some(false);
                        }
                        match rpc_resolve_agenda_item_blocking(
                            rpc_cmd_tx,
                            item_id,
                            current_multiplayer_room(app),
                        ) {
                            Ok(payload) => {
                                show_command_info_popup(app, raw, format_agenda_payload(&payload));
                                app.set_status(format!("Resolved agenda item #{item_id}"));
                            }
                            Err(e) => app.push_message(ChatMessage::error(format!(
                                "Failed to resolve agenda item #{item_id}: {e}"
                            ))),
                        }
                    }
                    _ => show_command_info_popup(
                        app,
                        raw,
                        "Usage: /collab agenda add <text>\n       /collab agenda list\n       /collab agenda done <item-id>"
                            .to_string(),
                    ),
                }
                return Some(false);
            }
            "hand" => {
                let action = args
                    .get(2)
                    .copied()
                    .unwrap_or("")
                    .trim()
                    .to_ascii_lowercase();
                let raised = match action.as_str() {
                    "raise" => true,
                    "lower" => false,
                    _ => {
                        show_command_info_popup(
                            app,
                            raw,
                            "Usage: /collab hand raise\n       /collab hand lower".to_string(),
                        );
                        return Some(false);
                    }
                };
                match rpc_set_hand_raised_blocking(
                    rpc_cmd_tx,
                    raised,
                    current_multiplayer_room(app),
                    None,
                ) {
                    Ok(payload) => {
                        let queue_position = payload
                            .get("queuePosition")
                            .and_then(|value| value.as_u64())
                            .unwrap_or(0);
                        if raised && queue_position > 0 {
                            app.set_status(format!(
                                "Hand raised. Queue position: {queue_position}"
                            ));
                        } else if raised {
                            app.set_status("Hand raised");
                        } else {
                            app.set_status("Hand lowered");
                        }
                    }
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to update hand raise state: {e}"
                    ))),
                }
                return Some(false);
            }
            "leave" => {
                return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/leave"));
            }
            "suggest" => {
                show_command_info_popup(app, raw, "Type `/suggest <text>` to send a suggestion to the driver.".to_string());
                return Some(false);
            }
            _ => {
                show_command_info_popup(app, raw, collab_usage_text().to_string());
                return Some(false);
            }
        }
    }

    // ── Pair mode commands ─────────────────────────────────────────────
    if lowered == "/pair" || lowered.starts_with("/pair ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() == 1 {
            return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/collab"));
        }
        if args.len() >= 2 && app.pair.mode_active && app.pair.is_host {
            let sub = args[1].to_ascii_lowercase();
            match sub.as_str() {
                "status" => {
                    match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                        Ok(payload) => {
                            show_command_info_popup(app, raw, format_host_server_payload(&payload))
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to fetch status: {e}"
                        ))),
                    }
                    return Some(false);
                }
                "members" | "who" => {
                    let room = if app.multiplayer.room.is_empty() {
                        None
                    } else {
                        Some(app.multiplayer.room.as_str())
                    };
                    match rpc_list_room_members_blocking(rpc_cmd_tx, room) {
                        Ok(payload) => {
                            show_command_info_popup(app, raw, format_room_members_payload(&payload))
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to fetch members: {e}"
                        ))),
                    }
                    return Some(false);
                }
                "kick" => {
                    if args.len() < 3 {
                        show_command_info_popup(
                            app,
                            raw,
                            "Usage: /pair kick <connection-id|number>".to_string(),
                        );
                        return Some(false);
                    }
                    let target = args[2];
                    let cid = if let Ok(num) = target.parse::<usize>() {
                        if num >= 1 && num <= app.pair.connected_users.len() {
                            app.pair.connected_users[num - 1].connection_id.clone()
                        } else {
                            show_command_info_popup(
                                app,
                                raw,
                                format!(
                                    "Invalid user number. Use 1-{}.",
                                    app.pair.connected_users.len()
                                ),
                            );
                            return Some(false);
                        }
                    } else {
                        target.to_string()
                    };
                    let room = if app.multiplayer.room.is_empty() {
                        None
                    } else {
                        Some(app.multiplayer.room.as_str())
                    };
                    match rpc_kick_member_blocking(rpc_cmd_tx, &cid, room) {
                        Ok(_) => show_command_info_popup(
                            app,
                            raw,
                            format!("Kicked `{cid}` from session."),
                        ),
                        Err(e) => {
                            app.push_message(ChatMessage::error(format!("Failed to kick: {e}")))
                        }
                    }
                    return Some(false);
                }
                "share" => {
                    match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                        Ok(payload) => {
                            let role = args.get(2).copied();
                            let room = if app.multiplayer.room.is_empty() {
                                None
                            } else {
                                Some(app.multiplayer.room.as_str())
                            };
                            show_command_info_popup(
                                app,
                                raw,
                                format_host_share_payload(&payload, role, room),
                            );
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!(
                            "Failed to fetch share info: {e}"
                        ))),
                    }
                    return Some(false);
                }
                _ => {} // fall through to normal /pair logic
            }
        }
        if args.len() == 1 || (args.len() == 2 && args[1].eq_ignore_ascii_case("start")) {
            let lobby = false;
            match rpc_pair_start_blocking(rpc_cmd_tx, lobby) {
                Ok(payload) => {
                    let short_code = payload.get("shortCode").and_then(|v| v.as_str()).unwrap_or("");
                    let invite_code = payload.get("inviteCode").and_then(|v| v.as_str()).unwrap_or("");
                    app.pair.mode_active = true;
                    app.pair.is_host = true;
                    app.pair.short_code = short_code.to_string();
                    app.pair.invite_code = invite_code.to_string();
                    app.multiplayer.enabled = true;
                    app.multiplayer.room = short_code.to_string();
                    app.multiplayer.role = "prompter".to_string();
                    let _ = std::process::Command::new("pbcopy")
                        .stdin(std::process::Stdio::piped())
                        .spawn()
                        .and_then(|mut child| {
                            use std::io::Write;
                            if let Some(ref mut stdin) = child.stdin {
                                let _ = stdin.write_all(invite_code.as_bytes());
                            }
                            child.wait()
                        });
                    app.push_message(ChatMessage::system(format!(
                        "Pair session started! Room: {short_code}\nInvite code copied to clipboard.\n\nNext steps:\n- Share the invite code with your partner\n- Use /collab members to see who joined\n- Use /collab handoff to pass driver control\n- Type /collab to see all session actions"
                    )));
                    app.set_status(format!("Pair session: {short_code}"));
                }
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to start pair session: {e}\nCheck that no other session is running. Try /leave first."))),
            }
            return Some(false);
        }
        let has_lobby = args.contains(&"--lobby");
        if args.len() == 2 && has_lobby {
            match rpc_pair_start_blocking(rpc_cmd_tx, true) {
                Ok(payload) => {
                    let short_code = payload.get("shortCode").and_then(|v| v.as_str()).unwrap_or("");
                    let invite_code = payload.get("inviteCode").and_then(|v| v.as_str()).unwrap_or("");
                    app.pair.mode_active = true;
                    app.pair.is_host = true;
                    app.pair.short_code = short_code.to_string();
                    app.pair.invite_code = invite_code.to_string();
                    app.multiplayer.enabled = true;
                    app.multiplayer.room = short_code.to_string();
                    app.multiplayer.role = "prompter".to_string();
                    app.multiplayer.lobby_enabled = true;
                    let _ = std::process::Command::new("pbcopy")
                        .stdin(std::process::Stdio::piped())
                        .spawn()
                        .and_then(|mut child| {
                            use std::io::Write;
                            if let Some(ref mut stdin) = child.stdin {
                                let _ = stdin.write_all(invite_code.as_bytes());
                            }
                            child.wait()
                        });
                    app.push_message(ChatMessage::system(format!(
                        "Pair session started (lobby mode)! Room: {short_code}\nInvite code copied to clipboard.\n\nNext steps:\n- Share the invite code — joiners will wait in lobby\n- Use /collab approve or /collab deny to manage lobby\n- Type /collab to see all session actions"
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to start pair session: {e}\nCheck that no other session is running. Try /leave first."))),
            }
            return Some(false);
        }
        if args[1].eq_ignore_ascii_case("leave") {
            return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/leave"));
        }
        if args[1].eq_ignore_ascii_case("join") {
            return Some(dispatch(app, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state, "/join-server"));
        }
        let invite = args[1];
        let bootstrap = match multiplayer::decode_invite_code(invite) {
            Ok(bootstrap) => bootstrap,
            Err(e) => {
                show_command_info_popup(
                    app,
                    raw,
                    format!("{e}\nUse `/pair` to host, or paste the invite code from the host."),
                );
                return Some(false);
            }
        };
        app.set_status("Connecting to endpoint...");
        if let Err(e) = multiplayer::preflight_join_endpoint(&bootstrap.signaling_url) {
            app.push_message(ChatMessage::error(format!(
                "Join preflight failed: {e}\nCheck the invite code and try again."
            )));
            return Some(false);
        }
        app.pair.mode_active = true;
        app.pair.is_host = false;
        app.pair.short_code = bootstrap.room.clone();
        app.multiplayer.room = bootstrap.room.clone();
        app.multiplayer.role = "viewer".to_string();
        multiplayer::reconnect_to_remote_server(app, tx, rpc_cmd_tx, launch, &bootstrap);
        app.push_message(ChatMessage::system(format!(
            "Joining pair session: {}",
            bootstrap.room
        )));
        return Some(false);
    }

    if lowered == "/pass" || lowered.starts_with("/pass ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let (display_name, connection_id): (Option<String>, Option<String>) = if args.len() > 1 {
            let target = args[1..].join(" ");
            if let Ok(num) = target.parse::<usize>() {
                if num >= 1 && num <= app.pair.connected_users.len() {
                    (
                        None,
                        Some(app.pair.connected_users[num - 1].connection_id.clone()),
                    )
                } else {
                    app.push_message(ChatMessage::error(format!(
                        "Invalid user number {num}. Use 1-{} per the presence bar.",
                        app.pair.connected_users.len()
                    )));
                    return Some(false);
                }
            } else if target.starts_with('@') {
                (Some(target.strip_prefix('@').unwrap().to_string()), None)
            } else {
                (Some(target.clone()), None)
            }
        } else {
            (None, None)
        };
        let room = if app.multiplayer.room.is_empty() {
            None
        } else {
            Some(app.multiplayer.room.as_str())
        };
        match rpc_pass_driver_blocking(
            rpc_cmd_tx,
            display_name.as_deref(),
            connection_id.as_deref(),
            room,
        ) {
            Ok(payload) => {
                let target_id = payload
                    .get("connectionId")
                    .and_then(|v| v.as_str())
                    .unwrap_or("someone");
                app.push_message(ChatMessage::system(format!(
                    "Driver role passed to `{target_id}`."
                )));
                app.set_status("Driver role handed off");
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to pass driver: {e}\nEnsure you are the driver. Use /who to check roles."
            ))),
        }
        return Some(false);
    }

    if lowered.starts_with("/suggest ") {
        let text = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if text.is_empty() {
            show_command_info_popup(app, raw, "Usage: /suggest <text>".to_string());
            return Some(false);
        }
        match rpc_suggest_text_blocking(rpc_cmd_tx, text) {
            Ok(payload) => {
                let mode = payload
                    .get("mode")
                    .and_then(|value| value.as_str())
                    .unwrap_or("suggestion");
                if mode == "agenda" {
                    app.set_status("Suggestion added to the shared agenda");
                } else {
                    app.set_status("Suggestion sent");
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Suggest failed: {e}\nEnsure you are connected to a collaboration session."
            ))),
        }
        return Some(false);
    }
    if lowered == "/suggest" {
        show_command_info_popup(
            app,
            raw,
            "Usage: /suggest <text>\nSend a suggestion to the active driver. In review rooms it is added to the shared agenda."
                .to_string(),
        );
        return Some(false);
    }

    if lowered == "/leave" {
        let host_running = rpc_get_host_server_status_blocking(rpc_cmd_tx)
            .ok()
            .and_then(|payload| payload.get("running").and_then(|value| value.as_bool()))
            .unwrap_or(false);
        if app.pair.is_host || host_running {
            match rpc_stop_host_server_blocking(rpc_cmd_tx) {
                Ok(_) => app.push_message(ChatMessage::system(
                    "Collaboration session stopped.".to_string(),
                )),
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to stop collaboration session: {e}\nThe session may have already ended."
                ))),
            }
        } else {
            app.push_message(ChatMessage::system(
                "Disconnected from collaboration session.".to_string(),
            ));
        }
        app.reset_pair_state();
        app.multiplayer.enabled = false;
        app.multiplayer.room.clear();
        app.multiplayer.role.clear();
        return Some(false);
    }

    if lowered == "/join-server" || lowered.starts_with("/join-server ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() == 1 {
            app.join_wizard_active = true;
            app.join_wizard_step = 0;
            app.join_wizard_input.clear();
            app.join_wizard_error.clear();
            app.mode = AppMode::Overlay;
            app.overlay_kind = Some(poor_cli_tui::app::OverlayKind::JoinWizard);
            return Some(false);
        }

        if args.len() == 2
            && matches!(
                args[1].to_ascii_lowercase().as_str(),
                "cancel" | "abort" | "stop"
            )
        {
            app.join_wizard_active = false;
            app.join_wizard_step = 0;
            app.join_wizard_input.clear();
            app.join_wizard_error.clear();
            show_command_info_popup(app, raw, "Join wizard cancelled.".to_string());
            return Some(false);
        }

        let bootstrap = match multiplayer::parse_join_server_args(raw) {
            Ok(values) => values,
            Err(error_message) => {
                show_command_info_popup(app, raw, error_message);
                return Some(false);
            }
        };

        app.set_status("Connecting to endpoint...");
        if let Err(e) = multiplayer::preflight_join_endpoint(&bootstrap.signaling_url) {
            app.push_message(ChatMessage::error(format!(
                "Join preflight failed: {e}\nUse `/collab join` for the invite prompt."
            )));
            return Some(false);
        }

        multiplayer::reconnect_to_remote_server(app, tx, rpc_cmd_tx, launch, &bootstrap);
        return Some(false);
    }

    if lowered == "/kick" || lowered.starts_with("/kick ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() < 2 || args.len() > 3 {
            show_command_info_popup(
                app,
                raw,
                "Usage: /kick <connection-id|#N|@name> [room]\nIf room is omitted, the current collaboration room is used."
                    .to_string(),
            );
            return Some(false);
        }

        let connection_id = args[1];
        let room = if let Some(explicit_room) = args.get(2).copied() {
            Some(explicit_room)
        } else if app.multiplayer.room.is_empty() {
            None
        } else {
            Some(app.multiplayer.room.as_str())
        };

        match rpc_kick_member_blocking(rpc_cmd_tx, connection_id, room) {
            Ok(payload) => {
                let room_name = payload
                    .get("room")
                    .and_then(|value| value.as_str())
                    .or(room)
                    .unwrap_or("");
                show_command_info_popup(
                    app,
                    raw,
                    format!("Kicked `{connection_id}` from room `{room_name}`."),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to kick `{connection_id}`: {e}\nUse /who to verify the member reference."
            ))),
        }
        return Some(false);
    }

    if lowered == "/who"
        || lowered.starts_with("/who ")
        || lowered == "/members"
        || lowered.starts_with("/members ")
    {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() > 2 {
            show_command_info_popup(app, raw, "Usage: /who [room]".to_string());
            return Some(false);
        }

        let room = if let Some(explicit_room) = args.get(1).copied() {
            Some(explicit_room)
        } else if app.multiplayer.room.is_empty() {
            None
        } else {
            Some(app.multiplayer.room.as_str())
        };

        match rpc_list_room_members_blocking(rpc_cmd_tx, room) {
            Ok(payload) => show_command_info_popup(app, raw, format_room_members_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch room members: {e}\nEnsure a multiplayer session is active."
            ))),
        }
        return Some(false);
    }

    if lowered == "/host-server" || lowered.starts_with("/host-server ") {
        return Some(handle_host_server(app, raw, lowered, rpc_cmd_tx));
    }

    if lowered == "/service" || lowered.starts_with("/service ") {
        return Some(handle_service(app, raw, lowered, rpc_cmd_tx));
    }

    if lowered == "/ollama" || lowered.starts_with("/ollama ") {
        return Some(handle_ollama(app, raw, lowered, rpc_cmd_tx));
    }

    None
}

// ── /host-server sub-handler ─────────────────────────────────────────

fn handle_host_server(
    app: &mut App,
    raw: &str,
    _lowered: &str,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
) -> bool {
    let args: Vec<&str> = raw.split_whitespace().collect();
    let subcommand = args.get(1).copied().unwrap_or("").trim();
    let lowered_subcommand = subcommand.to_ascii_lowercase();

    if lowered_subcommand.is_empty() {
        let server_running = rpc_get_host_server_status_blocking(rpc_cmd_tx).is_ok();
        let items = if server_running {
            vec![
                ListSelectorItem { label: "status: Show server status".into(), value: "status".into() },
                ListSelectorItem { label: "stop: Stop the server".into(), value: "stop".into() },
                ListSelectorItem { label: "members: List connected users".into(), value: "members".into() },
                ListSelectorItem { label: "kick: Remove a user".into(), value: "kick".into() },
                ListSelectorItem { label: "role: Manage user roles".into(), value: "role".into() },
                ListSelectorItem { label: "share: Show invite info".into(), value: "share".into() },
                ListSelectorItem { label: "lobby: Manage lobby".into(), value: "lobby".into() },
                ListSelectorItem { label: "approve: Approve lobby request".into(), value: "approve".into() },
                ListSelectorItem { label: "deny: Deny lobby request".into(), value: "deny".into() },
                ListSelectorItem { label: "rotate-token: Rotate invite token".into(), value: "rotate-token".into() },
                ListSelectorItem { label: "revoke: Revoke invite code".into(), value: "revoke".into() },
                ListSelectorItem { label: "handoff: Transfer host role".into(), value: "handoff".into() },
                ListSelectorItem { label: "preset: Set server preset".into(), value: "preset".into() },
                ListSelectorItem { label: "activity: Show activity log".into(), value: "activity".into() },
            ]
        } else {
            vec![
                ListSelectorItem { label: "start: Start a new server".into(), value: "start".into() },
            ]
        };
        app.open_list_selector(ListSelectorState {
            title: "Host Server".into(), items, selected_idx: 0,
            command_template: "/host-server {}".to_string(),
            action_hint_override: None,
        });
        return false;
    }

    // Delegate all subcommands inline -- this is already a very long block.
    // For brevity, re-dispatch via the original handle_slash_command which still has this code.
    // Actually, we need the full logic here. Let me include the key subcommands.

    if lowered_subcommand == "status" {
        if args.len() > 2 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
            Ok(payload) => show_command_info_popup(app, raw, format_host_server_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch host server status: {e}\nUse /host-server to start a server first."))),
        }
        return false;
    }
    if lowered_subcommand == "stop" {
        if args.len() > 2 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        match rpc_stop_host_server_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                if payload.get("stopped").and_then(|v| v.as_bool()).unwrap_or(false) {
                    show_command_info_popup(app, raw, "Multiplayer host stopped.".to_string());
                } else {
                    show_command_info_popup(app, raw, "No multiplayer host is currently running.".to_string());
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to stop host server: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "members" || lowered_subcommand == "users" {
        if args.len() > 3 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let room = args.get(2).copied();
        match rpc_list_host_members_blocking(rpc_cmd_tx, room) {
            Ok(payload) => show_command_info_popup(app, raw, format_host_members_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch host members: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "kick" || lowered_subcommand == "remove" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let connection_id = args[2];
        let room = args.get(3).copied();
        match rpc_remove_host_member_blocking(rpc_cmd_tx, connection_id, room) {
            Ok(payload) => {
                let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or(""));
                let mut lines = vec![format!("Removed connection `{connection_id}` from room `{room_name}`.")];
                if let Ok(updated) = rpc_list_host_members_blocking(rpc_cmd_tx, if room_name.is_empty() { None } else { Some(room_name) }) {
                    lines.push(String::new());
                    lines.push(format_host_members_payload(&updated));
                }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to remove `{connection_id}`: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "role" || lowered_subcommand == "promote" || lowered_subcommand == "demote" {
        let (connection_id, role, room): (&str, &str, Option<&str>) =
            if lowered_subcommand == "role" {
                if args.len() < 4 || args.len() > 5 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
                (args[2], args[3], args.get(4).copied())
            } else if lowered_subcommand == "promote" {
                if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
                (args[2], "prompter", args.get(3).copied())
            } else {
                if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
                (args[2], "viewer", args.get(3).copied())
            };
        let normalized_role = match role.to_ascii_lowercase().as_str() {
            "viewer" | "read" | "read-only" => "viewer",
            "prompter" | "writer" | "editor" | "admin" => "prompter",
            _ => { show_command_info_popup(app, raw, "Invalid role. Use `viewer` or `prompter`.".to_string()); return false; }
        };
        match rpc_set_host_member_role_blocking(rpc_cmd_tx, connection_id, normalized_role, room) {
            Ok(payload) => {
                let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or(""));
                let mut lines = vec![format!("Updated `{connection_id}` to role **{normalized_role}** in room `{room_name}`.")];
                if let Ok(updated) = rpc_list_host_members_blocking(rpc_cmd_tx, if room_name.is_empty() { None } else { Some(room_name) }) {
                    lines.push(String::new());
                    lines.push(format_host_members_payload(&updated));
                }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to update role for `{connection_id}`: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "share" {
        if args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let mut role_filter: Option<&str> = None;
        let mut room_filter: Option<&str> = None;
        if let Some(first) = args.get(2).copied() {
            let first_lower = first.to_ascii_lowercase();
            if first_lower == "viewer" || first_lower == "prompter" {
                role_filter = Some(first); room_filter = args.get(3).copied();
            } else {
                room_filter = Some(first);
                if let Some(second) = args.get(3).copied() {
                    let second_lower = second.to_ascii_lowercase();
                    if second_lower == "viewer" || second_lower == "prompter" { role_filter = Some(second); }
                }
            }
        }
        match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
            Ok(payload) => show_command_info_popup(app, raw, format_host_share_payload(&payload, role_filter, room_filter)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to get host share details: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "lobby" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let enable = match args[2].to_ascii_lowercase().as_str() {
            "on" | "enable" | "enabled" | "true" => true,
            "off" | "disable" | "disabled" | "false" => false,
            _ => { show_command_info_popup(app, raw, "Usage: /host-server lobby <on|off> [room]".to_string()); return false; }
        };
        let room = args.get(3).copied();
        match rpc_set_host_lobby_blocking(rpc_cmd_tx, enable, room) {
            Ok(payload) => {
                let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or(""));
                let state = if enable { "enabled" } else { "disabled" };
                show_command_info_popup(app, raw, format!("Lobby approvals {state} for room `{room_name}`."));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to update lobby mode: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "approve" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let connection_id = args[2]; let room = args.get(3).copied();
        match rpc_approve_host_member_blocking(rpc_cmd_tx, connection_id, room) {
            Ok(payload) => { let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or("")); show_command_info_popup(app, raw, format!("Approved `{connection_id}` in room `{room_name}`.")); }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to approve member `{connection_id}`: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "deny" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let connection_id = args[2]; let room = args.get(3).copied();
        match rpc_deny_host_member_blocking(rpc_cmd_tx, connection_id, room) {
            Ok(payload) => { let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or("")); show_command_info_popup(app, raw, format!("Denied `{connection_id}` in room `{room_name}`.")); }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to deny member `{connection_id}`: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "rotate-token" {
        if args.len() < 3 || args.len() > 5 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let role = args[2].to_ascii_lowercase();
        if role != "viewer" && role != "prompter" { show_command_info_popup(app, raw, "Usage: /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]".to_string()); return false; }
        let mut room: Option<&str> = None; let mut expiry_seconds: Option<u64> = None;
        if let Some(arg3) = args.get(3).copied() { if let Ok(parsed) = arg3.parse::<u64>() { expiry_seconds = Some(parsed); } else { room = Some(arg3); } }
        if let Some(arg4) = args.get(4).copied() { match arg4.parse::<u64>() { Ok(parsed) => expiry_seconds = Some(parsed), Err(_) => { show_command_info_popup(app, raw, "Usage: /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]".to_string()); return false; } } }
        match rpc_rotate_host_token_blocking(rpc_cmd_tx, &role, room, expiry_seconds) {
            Ok(payload) => {
                let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or(""));
                let token = payload.get("token").and_then(|v| v.as_str()).unwrap_or("");
                let join_command = payload.get("joinCommand").and_then(|v| v.as_str()).unwrap_or("");
                let invite_code = payload.get("inviteCode").and_then(|v| v.as_str()).unwrap_or("");
                let mut lines = vec![format!("Rotated **{role}** token for room `{room_name}`: `{token}`")];
                if !join_command.is_empty() { lines.push(format!("- Join command: `{join_command}`")); }
                if !invite_code.is_empty() { lines.push(format!("- Invite code: `{invite_code}`")); }
                if let Some(expires_at) = payload.get("expiresAt").and_then(|v| v.as_str()) { if !expires_at.is_empty() { lines.push(format!("- Expires at: `{expires_at}`")); } }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to rotate token: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "revoke" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let value = args[2]; let room = args.get(3).copied();
        match rpc_revoke_host_token_blocking(rpc_cmd_tx, value, room) {
            Ok(payload) => { let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or("")); let kind = payload.get("kind").and_then(|v| v.as_str()).unwrap_or("token"); show_command_info_popup(app, raw, format!("Revoked `{value}` ({kind}) in room `{room_name}`.")); }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to revoke `{value}`: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "handoff" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let connection_id = args[2]; let room = args.get(3).copied();
        match rpc_handoff_host_member_blocking(rpc_cmd_tx, connection_id, room) {
            Ok(payload) => { let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or("")); show_command_info_popup(app, raw, format!("Handed off prompter role to `{connection_id}` in room `{room_name}`.")); }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to handoff to `{connection_id}`: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "preset" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let preset = args[2].to_ascii_lowercase();
        if preset != "pairing" && preset != "mob" && preset != "review" { show_command_info_popup(app, raw, "Usage: /host-server preset <pairing|mob|review> [room]".to_string()); return false; }
        let room = args.get(3).copied();
        match rpc_set_host_preset_blocking(rpc_cmd_tx, &preset, room) {
            Ok(payload) => {
                let room_name = payload.get("room").and_then(|v| v.as_str()).unwrap_or(room.unwrap_or(""));
                let lobby_enabled = payload.get("lobbyEnabled").and_then(|v| v.as_bool()).unwrap_or(false);
                show_command_info_popup(app, raw, format!("Applied preset **{preset}** to room `{room_name}` (lobby: {}).", if lobby_enabled { "on" } else { "off" }));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to set preset: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "activity" {
        if args.len() > 5 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
        let mut room: Option<&str> = None; let mut limit: u64 = 30; let mut event_type: Option<&str> = None; let mut idx = 2usize;
        if let Some(arg) = args.get(idx).copied() { if arg.parse::<u64>().is_err() { room = Some(arg); idx += 1; } }
        if let Some(arg) = args.get(idx).copied() { if let Ok(parsed) = arg.parse::<u64>() { limit = parsed; idx += 1; } }
        if let Some(arg) = args.get(idx).copied() { event_type = Some(arg); idx += 1; }
        if idx < args.len() { show_command_info_popup(app, raw, "Usage: /host-server activity [room] [limit] [event-type]".to_string()); return false; }
        match rpc_list_host_activity_blocking(rpc_cmd_tx, room, limit, event_type) {
            Ok(payload) => show_command_info_popup(app, raw, format_host_activity_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch host activity: {e}"))),
        }
        return false;
    }
    if lowered_subcommand == "help" { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; }
    if lowered_subcommand == "start" {
        match rpc_start_host_server_blocking(rpc_cmd_tx, None) {
            Ok(payload) => show_command_info_popup(app, raw, format_host_server_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to start host server: {e}"))),
        }
        return false;
    }

    // fallback: treat subcommand as room name
    let room = if subcommand.is_empty() { None } else { if args.len() > 2 { show_command_info_popup(app, raw, host_server_usage_text().to_string()); return false; } Some(subcommand) };
    match rpc_start_host_server_blocking(rpc_cmd_tx, room) {
        Ok(payload) => show_command_info_popup(app, raw, format_host_server_payload(&payload)),
        Err(e) => app.push_message(ChatMessage::error(format!("Failed to start host server: {e}"))),
    }
    false
}

// ── /service sub-handler ─────────────────────────────────────────────

fn handle_service(app: &mut App, raw: &str, _lowered: &str, rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>) -> bool {
    let args: Vec<&str> = raw.split_whitespace().collect();
    let subcommand = args.get(1).copied().unwrap_or("").trim().to_ascii_lowercase();
    if subcommand.is_empty() || subcommand == "help" {
        let items = vec![
            ListSelectorItem { label: "status: Show service status".into(), value: "status".into() },
            ListSelectorItem { label: "list: List all services".into(), value: "list".into() },
            ListSelectorItem { label: "start: Start a service".into(), value: "start".into() },
            ListSelectorItem { label: "stop: Stop a service".into(), value: "stop".into() },
            ListSelectorItem { label: "logs: View service logs".into(), value: "logs".into() },
        ];
        app.open_list_selector(ListSelectorState { title: "Service".into(), items, selected_idx: 0, command_template: "/service {}".to_string(), action_hint_override: None });
        return false;
    }
    if subcommand == "status" || subcommand == "list" {
        if args.len() > 3 { show_command_info_popup(app, raw, service_usage_text().to_string()); return false; }
        let service_name = args.get(2).copied();
        match rpc_get_service_status_blocking(rpc_cmd_tx, service_name) {
            Ok(payload) => show_command_info_popup(app, raw, format_service_status_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch service status: {e}"))),
        }
        return false;
    }
    if subcommand == "start" {
        let mut split = raw.splitn(4, ' '); let _ = split.next(); let _ = split.next();
        let service_name = split.next().unwrap_or("").trim();
        let command_text = split.next().map(str::trim).filter(|value| !value.is_empty());
        if service_name.is_empty() { show_command_info_popup(app, raw, service_usage_text().to_string()); return false; }
        match rpc_start_service_blocking(rpc_cmd_tx, service_name, command_text, None) {
            Ok(payload) => show_command_info_popup(app, raw, format_service_status_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to start service `{service_name}`: {e}"))),
        }
        return false;
    }
    if subcommand == "stop" {
        if args.len() != 3 { show_command_info_popup(app, raw, service_usage_text().to_string()); return false; }
        let service_name = args[2];
        match rpc_stop_service_blocking(rpc_cmd_tx, service_name) {
            Ok(payload) => show_command_info_popup(app, raw, format_service_status_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to stop service `{service_name}`: {e}"))),
        }
        return false;
    }
    if subcommand == "logs" {
        if args.len() < 3 || args.len() > 4 { show_command_info_popup(app, raw, service_usage_text().to_string()); return false; }
        let service_name = args[2];
        let line_count = match args.get(3) { Some(raw_count) => match raw_count.parse::<u64>() { Ok(parsed) => Some(parsed), Err(_) => { show_command_info_popup(app, raw, "lines must be an integer".to_string()); return false; } }, None => None };
        match rpc_get_service_logs_blocking(rpc_cmd_tx, service_name, line_count) {
            Ok(payload) => {
                let status_block = payload.get("status").map(format_service_status_payload).unwrap_or_else(|| format!("**Service:** `{service_name}`"));
                let log_path = payload.get("logPath").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                let content = payload.get("content").and_then(|v| v.as_str()).unwrap_or("");
                if content.is_empty() {
                    show_command_info_popup(app, raw, format!("{status_block}\n\nNo logs available yet at `{log_path}`."));
                } else {
                    app.last_command_output = Some(content.to_string());
                    show_command_info_popup(app, raw, format!("{status_block}\n\n**Log Tail:** `{log_path}`\n```text\n{}\n```", truncate_block(content, 3200)));
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch logs for `{service_name}`: {e}"))),
        }
        return false;
    }
    show_command_info_popup(app, raw, service_usage_text().to_string());
    false
}

// ── /ollama sub-handler ──────────────────────────────────────────────

fn handle_ollama(app: &mut App, raw: &str, _lowered: &str, rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>) -> bool {
    let args: Vec<&str> = raw.split_whitespace().collect();
    let subcommand = args.get(1).copied().unwrap_or("").trim().to_ascii_lowercase();
    if subcommand.is_empty() {
        let items = vec![
            ListSelectorItem { label: "status: Show Ollama status".into(), value: "status".into() },
            ListSelectorItem { label: "start: Start Ollama service".into(), value: "start".into() },
            ListSelectorItem { label: "stop: Stop Ollama service".into(), value: "stop".into() },
            ListSelectorItem { label: "list: List local models".into(), value: "list".into() },
            ListSelectorItem { label: "pull: Pull a model".into(), value: "pull".into() },
            ListSelectorItem { label: "logs: View Ollama logs".into(), value: "logs".into() },
            ListSelectorItem { label: "ps: Show running models".into(), value: "ps".into() },
        ];
        app.open_list_selector(ListSelectorState { title: "Ollama".into(), items, selected_idx: 0, command_template: "/ollama {}".to_string(), action_hint_override: None });
        return false;
    }
    match subcommand.as_str() {
        "status" => match rpc_get_service_status_blocking(rpc_cmd_tx, Some("ollama")) {
            Ok(payload) => show_command_info_popup(app, raw, format_service_status_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch Ollama status: {e}"))),
        },
        "start" => match rpc_start_service_blocking(rpc_cmd_tx, "ollama", None, None) {
            Ok(payload) => {
                let running = payload.get("running").and_then(|v| v.as_bool()).unwrap_or(false);
                let healthy = payload.get("healthy").and_then(|v| v.as_bool()).unwrap_or(false);
                let mut lines = vec![format_service_status_payload(&payload)]; lines.push(String::new());
                if running && healthy { lines.push("Next steps:".to_string()); lines.push("- `/switch` and choose `ollama`.".to_string()); lines.push("- If model is missing: `/ollama pull <model>`.".to_string()); }
                else if running { lines.push("Ollama process started but endpoint is not ready yet. Check `/ollama status`.".to_string()); }
                else { lines.push("Ollama did not report as running. Check `/ollama logs`.".to_string()); }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to start Ollama service: {e}"))),
        },
        "stop" => match rpc_stop_service_blocking(rpc_cmd_tx, "ollama") {
            Ok(payload) => show_command_info_popup(app, raw, format_service_status_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to stop Ollama service: {e}"))),
        },
        "logs" => {
            let line_count = match args.get(2) { Some(raw_count) => match raw_count.parse::<u64>() { Ok(parsed) => Some(parsed), Err(_) => { show_command_info_popup(app, raw, "lines must be an integer (e.g. `/ollama logs 120`)".to_string()); return false; } }, None => Some(120) };
            match rpc_get_service_logs_blocking(rpc_cmd_tx, "ollama", line_count) {
                Ok(payload) => {
                    let status_block = payload.get("status").map(format_service_status_payload).unwrap_or_else(|| "**Service:** `ollama`".to_string());
                    let log_path = payload.get("logPath").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                    let content = payload.get("content").and_then(|v| v.as_str()).unwrap_or("");
                    if content.is_empty() { show_command_info_popup(app, raw, format!("{status_block}\n\nNo logs available yet at `{log_path}`.")); }
                    else { app.last_command_output = Some(content.to_string()); show_command_info_popup(app, raw, format!("{status_block}\n\n**Log Tail:** `{log_path}`\n```text\n{}\n```", truncate_block(content, 3200))); }
                }
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch Ollama logs: {e}"))),
            }
        }
        "pull" => {
            if args.len() != 3 { show_command_info_popup(app, raw, "Usage: /ollama pull <model>".to_string()); return false; }
            let model = args[2];
            let command = format!("ollama pull {model}");
            match rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, &command, Some(1800), 1815) {
                Ok(output) => show_command_info_popup(app, raw, format!("**Command:** `{command}`\n\n```text\n{}\n```", truncate_block(&output, 3200))),
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to pull Ollama model `{model}`: {e}"))),
            }
        }
        "list" | "list-models" => {
            let (reply_tx, reply_rx) = mpsc::sync_channel(1);
            let _ = rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx });
            match reply_rx.recv_timeout(Duration::from_secs(20)) {
                Ok(Ok(providers)) => {
                    let ollama = providers.iter().find(|provider| provider.name.eq_ignore_ascii_case("ollama"));
                    if let Some(provider) = ollama {
                        if provider.models.is_empty() { show_command_info_popup(app, raw, "No installed Ollama models were detected.\n\nTry `/ollama pull <model>`.".to_string()); }
                        else { let mut lines = vec!["**Installed Ollama Models**".to_string()]; lines.extend(provider.models.iter().map(|model| format!("- `{model}`"))); show_command_info_popup(app, raw, lines.join("\n")); }
                    } else { app.push_message(ChatMessage::error("Failed to list Ollama models: provider metadata unavailable".to_string())); }
                }
                Ok(Err(e)) => app.push_message(ChatMessage::error(format!("Failed to list Ollama models: {e}"))),
                Err(_) => app.push_message(ChatMessage::error("Failed to list Ollama models: timed out waiting for provider metadata".to_string())),
            }
        }
        "ps" => {
            match rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, "ollama ps", Some(60), 75) {
                Ok(output) => show_command_info_popup(app, raw, format!("**Ollama Running Models**\n```text\n{}\n```", truncate_block(&output, 3200))),
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to inspect Ollama running models: {e}"))),
            }
        }
        _ => show_command_info_popup(app, raw, ollama_usage_text().to_string()),
    }
    false
}
