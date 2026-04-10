use super::*;

pub(crate) fn bool_icon(value: Option<bool>) -> &'static str {
    if value.unwrap_or(false) {
        "✓"
    } else {
        "✗"
    }
}

pub(crate) fn bool_label(value: bool) -> &'static str {
    if value {
        "on"
    } else {
        "off"
    }
}

pub(crate) fn format_value_for_display(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        Value::Array(_) | Value::Object(_) => {
            serde_json::to_string(value).unwrap_or_else(|_| "<unserializable>".to_string())
        }
    }
}

pub(crate) fn format_host_server_payload(payload: &Value) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No collaboration host is running.\nUse `/collab start mob` to start one.".to_string();
    }

    let created = payload
        .get("created")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let bind_host = payload
        .get("bindHost")
        .and_then(|v| v.as_str())
        .unwrap_or("0.0.0.0");
    let port = payload.get("port").and_then(|v| v.as_u64()).unwrap_or(0);
    let local_signaling = payload
        .get("localSignalingUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let share_signaling = payload
        .get("shareSignalingUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let public_signaling = payload
        .get("publicSignalingUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    let mut lines = vec![
        if created {
            "Multiplayer host started.".to_string()
        } else {
            "Multiplayer host is already running.".to_string()
        },
        format!("Bind: `{bind_host}:{port}`"),
    ];

    if !local_signaling.is_empty() {
        lines.push(format!("Local signaling: `{local_signaling}`"));
    }
    if !share_signaling.is_empty() {
        lines.push(format!("LAN signaling: `{share_signaling}`"));
        if bind_host == "0.0.0.0" && share_signaling.contains("127.0.0.1") {
            lines.push(
                "**⚠ ACTION REQUIRED:** LAN IP detection fell back to localhost. Replace `127.0.0.1` with your actual LAN IP before sharing."
                    .to_string(),
            );
        }
    }
    if !public_signaling.is_empty() {
        lines.push(format!("Public signaling: `{public_signaling}`"));
    }

    let rooms = payload
        .get("rooms")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    if rooms.is_empty() {
        lines.push(String::new());
        lines.push("No multiplayer rooms are available yet.".to_string());
        return lines.join("\n");
    }

    for room in rooms {
        let name = room
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let viewer_join = room
            .get("viewerJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_join = room
            .get("prompterJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let signaling_url = room
            .get("signalingUrl")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let viewer_code = room
            .get("viewerInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_code = room
            .get("prompterInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let member_count = room
            .get("memberCount")
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        let lobby_enabled = room
            .get("lobbyEnabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let preset = room
            .get("preset")
            .and_then(|v| v.as_str())
            .unwrap_or("pairing");

        lines.push(String::new());
        lines.push(format!(
            "**Room `{name}`** ({member_count} member(s), lobby: {}, preset: `{preset}`)",
            if lobby_enabled { "on" } else { "off" }
        ));
        if !signaling_url.is_empty() {
            lines.push(format!("- Signaling endpoint: `{signaling_url}`"));
        }
        if !viewer_join.is_empty() {
            lines.push(format!("- Share viewer command: `{viewer_join}`"));
        }
        if !prompter_join.is_empty() {
            lines.push(format!("- Share prompter command: `{prompter_join}`"));
        }
        if !viewer_code.is_empty() {
            lines.push(format!("- Viewer invite code: `{viewer_code}`"));
        }
        if !prompter_code.is_empty() {
            lines.push(format!("- Prompter invite code: `{prompter_code}`"));
        }
    }

    lines.join("\n")
}

pub(crate) fn format_host_share_payload(
    payload: &Value,
    role_filter: Option<&str>,
    room_filter: Option<&str>,
) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No collaboration host is running.\nUse `/collab start mob` to start one.".to_string();
    }

    let rooms = payload
        .get("rooms")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    if rooms.is_empty() {
        return "No multiplayer rooms are available yet.".to_string();
    }

    let normalized_role = role_filter.map(|role| role.to_ascii_lowercase());
    let normalized_room = room_filter.map(|room| room.trim().to_string());
    let mut lines = vec!["**Host Share Payloads**".to_string()];
    let mut matched = 0usize;

    for room in rooms {
        let room_name = room
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        if let Some(filter) = &normalized_room {
            if filter != room_name {
                continue;
            }
        }

        let viewer_join = room
            .get("viewerJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_join = room
            .get("prompterJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let viewer_code = room
            .get("viewerInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_code = room
            .get("prompterInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        lines.push(String::new());
        lines.push(format!("**Room `{room_name}`**"));

        if normalized_role.is_none() || normalized_role.as_deref() == Some("viewer") {
            matched += 1;
            lines.push("- Viewer share command:".to_string());
            if viewer_join.is_empty() {
                lines.push("```text\n(unavailable)\n```".to_string());
            } else {
                lines.push(format!("```text\n{viewer_join}\n```"));
            }
            if !viewer_code.is_empty() {
                lines.push(format!("- Viewer invite code: `{viewer_code}`"));
                lines.push(format!(
                    "- Viewer QR payload: `poor-cli://join?code={viewer_code}`"
                ));
            }
        }

        if normalized_role.is_none() || normalized_role.as_deref() == Some("prompter") {
            matched += 1;
            lines.push("- Prompter share command:".to_string());
            if prompter_join.is_empty() {
                lines.push("```text\n(unavailable)\n```".to_string());
            } else {
                lines.push(format!("```text\n{prompter_join}\n```"));
            }
            if !prompter_code.is_empty() {
                lines.push(format!("- Prompter invite code: `{prompter_code}`"));
                lines.push(format!(
                    "- Prompter QR payload: `poor-cli://join?code={prompter_code}`"
                ));
            }
        }
    }

    if matched == 0 {
        return "No share payloads matched your filters.\nUsage: `/host-server share [viewer|prompter] [room]`".to_string();
    }

    lines.push(String::new());
    lines.push("Tip: use `/copy` right after this to copy the latest share payload.".to_string());
    lines.join("\n")
}

pub(crate) fn host_server_usage_text() -> &'static str {
    "Usage: /host-server [room]\n\
       /host-server status\n\
       /host-server stop\n\
       /host-server share [viewer|prompter] [room]\n\
       /host-server members [room]\n\
       /host-server kick <connection-id> [room]\n\
       /host-server role <connection-id> <viewer|prompter> [room]\n\
       /host-server promote <connection-id> [room]\n\
       /host-server demote <connection-id> [room]\n\
       /host-server lobby <on|off> [room]\n\
       /host-server approve <connection-id> [room]\n\
       /host-server deny <connection-id> [room]\n\
       /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]\n\
       /host-server revoke <token|connection-id> [room]\n\
       /host-server handoff <connection-id> [room]\n\
       /host-server preset <pairing|mob|review> [room]\n\
       /host-server activity [room] [limit] [event-type]"
}

pub(crate) fn format_host_activity_payload(payload: &Value) -> String {
    let room = payload
        .get("room")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown");
    let event_filter = payload
        .get("eventType")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let events = payload
        .get("events")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    if events.is_empty() {
        return format!("No activity events found for room `{room}`.");
    }

    let mut lines = vec![format!(
        "**Host Activity** room `{room}` ({})",
        events.len()
    )];
    if !event_filter.is_empty() {
        lines.push(format!("Filter: `{event_filter}`"));
    }
    for event in events {
        let timestamp = event
            .get("timestamp")
            .and_then(|v| v.as_str())
            .unwrap_or("-");
        let event_type = event
            .get("eventType")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let actor = event.get("actor").and_then(|v| v.as_str()).unwrap_or("");
        let request_id = event
            .get("requestId")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let mut line = format!("- `{timestamp}` **{event_type}**");
        if !actor.is_empty() {
            line.push_str(&format!(" actor=`{actor}`"));
        }
        if !request_id.is_empty() {
            line.push_str(&format!(" request=`{request_id}`"));
        }
        if let Some(details) = event.get("details").and_then(|v| v.as_object()) {
            if !details.is_empty() {
                let details_text = details
                    .iter()
                    .map(|(key, value)| format!("{key}={}", value))
                    .collect::<Vec<_>>()
                    .join(", ");
                line.push_str(&format!(" details: {details_text}"));
            }
        }
        lines.push(line);
    }
    lines.join("\n")
}

pub(crate) fn format_host_members_payload(payload: &Value) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No collaboration host is running.\nUse `/collab start mob` to start one.".to_string();
    }

    let rooms = payload
        .get("rooms")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    if rooms.is_empty() {
        return "No active rooms found on host.".to_string();
    }

    let mut lines = vec!["**Host Members**".to_string()];
    for room in rooms {
        let room_name = room
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let member_count = room
            .get("memberCount")
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        let lobby_enabled = room
            .get("lobbyEnabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let preset = room
            .get("preset")
            .and_then(|v| v.as_str())
            .unwrap_or("pairing");
        lines.push(String::new());
        lines.push(format!(
            "**Room `{room_name}`** ({member_count} member(s), lobby: {}, preset: `{preset}`)",
            if lobby_enabled { "on" } else { "off" }
        ));

        let members = room
            .get("members")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        if members.is_empty() {
            lines.push("- No connected members".to_string());
            continue;
        }

        for member in members {
            let connection_id = member
                .get("connectionId")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let role = member
                .get("role")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let client_name = member
                .get("clientName")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .trim();
            let active = member
                .get("active")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let connected = member
                .get("connected")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let joined_at = member
                .get("joinedAt")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let approved = member
                .get("approved")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);

            let state = if connected {
                "connected"
            } else {
                "disconnected"
            };
            let active_label = if active { ", active" } else { "" };
            let approved_label = if approved { "" } else { ", pending-approval" };
            let name_label = if client_name.is_empty() {
                String::new()
            } else {
                format!(" ({client_name})")
            };

            lines.push(format!(
                "- `{connection_id}`{name_label}: **{role}** ({state}{active_label}{approved_label})"
            ));
            if !joined_at.is_empty() {
                lines.push(format!("  joined: `{joined_at}`"));
            }
        }
    }

    lines.join("\n")
}

pub(crate) fn format_room_members_payload(payload: &Value) -> String {
    let room = payload
        .get("room")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let mode = payload
        .get("mode")
        .and_then(|value| value.as_str())
        .unwrap_or("pair");
    let agenda_summary = payload
        .get("agendaSummary")
        .and_then(|value| value.as_object())
        .cloned()
        .unwrap_or_default();
    let agenda_open = agenda_summary
        .get("open")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let agenda_total = agenda_summary
        .get("total")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let hands_raised = payload
        .get("handsRaised")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    let members = payload
        .get("members")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();

    let mut lines = vec![
        format!("**Collaboration Status** room `{room}`"),
        format!("- Mode: `{mode}`"),
        format!("- Members: {}", members.len()),
    ];
    if agenda_total > 0 {
        lines.push(format!(
            "- Agenda: {agenda_open} open / {agenda_total} total"
        ));
    }
    if !hands_raised.is_empty() {
        let raised = hands_raised
            .iter()
            .filter_map(|value| value.as_str())
            .collect::<Vec<_>>()
            .join(", ");
        if !raised.is_empty() {
            lines.push(format!("- Hands raised: {raised}"));
        }
    }

    if members.is_empty() {
        lines.push("- No members connected".to_string());
        return lines.join("\n");
    }

    lines.push(String::new());
    lines.push("**Members**".to_string());
    for member in members {
        let connection_id = member
            .get("connection_id")
            .or_else(|| member.get("connectionId"))
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let display_name = member
            .get("display_name")
            .or_else(|| member.get("displayName"))
            .and_then(|value| value.as_str())
            .unwrap_or(connection_id);
        let role = member
            .get("ui_role")
            .or_else(|| member.get("uiRole"))
            .or_else(|| member.get("role"))
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let approval_state = member
            .get("approval_state")
            .or_else(|| member.get("approvalState"))
            .and_then(|value| value.as_str())
            .unwrap_or("approved");
        let active_prompter = member
            .get("is_active_prompter")
            .or_else(|| member.get("active"))
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        let hand_raised = member
            .get("hand_raised")
            .or_else(|| member.get("handRaised"))
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        let queue_position = member
            .get("queue_position")
            .or_else(|| member.get("queuePosition"))
            .and_then(|value| value.as_u64())
            .unwrap_or(0);

        let mut tags = vec![format!("role=`{role}`")];
        if active_prompter {
            tags.push("active".to_string());
        }
        if approval_state != "approved" {
            tags.push(format!("approval=`{approval_state}`"));
        }
        if hand_raised {
            if queue_position > 0 {
                tags.push(format!("hand-raised#{}", queue_position));
            } else {
                tags.push("hand-raised".to_string());
            }
        }
        lines.push(format!(
            "- `{display_name}` (`{connection_id}`) {}",
            tags.join(" ")
        ));
    }
    lines.join("\n")
}

pub(crate) fn format_agenda_payload(payload: &Value) -> String {
    let room = payload
        .get("room")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let agenda_summary = payload
        .get("agendaSummary")
        .and_then(|value| value.as_object())
        .cloned()
        .unwrap_or_default();
    let agenda_open = agenda_summary
        .get("open")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let agenda_total = agenda_summary
        .get("total")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let items = payload
        .get("items")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();

    let mut lines = vec![format!("**Shared Agenda** room `{room}`")];
    if agenda_total > 0 {
        lines.push(format!("- {agenda_open} open / {agenda_total} total"));
    }
    if items.is_empty() {
        lines.push("- No agenda items yet".to_string());
        return lines.join("\n");
    }

    for item in items {
        let item_id = item
            .get("id")
            .and_then(|value| value.as_u64())
            .map(|value| value.to_string())
            .unwrap_or_else(|| "?".to_string());
        let text = item
            .get("text")
            .and_then(|value| value.as_str())
            .unwrap_or("(untitled)");
        let author = item
            .get("author")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        let resolved = item
            .get("resolved")
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        let status = if resolved { "done" } else { "open" };
        if author.is_empty() {
            lines.push(format!("- #{item_id} [{status}] {text}"));
        } else {
            lines.push(format!("- #{item_id} [{status}] {text} ({author})"));
        }
    }

    lines.join("\n")
}

pub(crate) fn service_usage_text() -> &'static str {
    "Usage: /service status [name]\n\
       /service start <name> [command...]\n\
       /service stop <name>\n\
       /service logs <name> [lines]"
}

pub(crate) fn ollama_usage_text() -> &'static str {
    "Usage: /ollama start|stop|status\n\
       /ollama logs [lines]\n\
       /ollama pull <model>\n\
       /ollama list-models"
}

pub(crate) fn ollama_recovery_popup(error_message: &str, model_name: &str) -> Option<(String, String)> {
    let lowered = error_message.to_ascii_lowercase();

    if lowered.contains("cannot connect to host")
        || lowered.contains("ollama server not available")
        || lowered.contains("connect call failed")
    {
        return Some((
            "Ollama Not Reachable".to_string(),
            "The Ollama server is not reachable at `http://localhost:11434`.\n\n\
Run:\n\
- `/ollama start`\n\
- `/ollama status`\n\
- `/ollama logs`\n\n\
If startup fails, run `/service status ollama` to verify the executable path and logs."
                .to_string(),
        ));
    }

    if lowered.contains("model")
        && lowered.contains("not found")
        && (lowered.contains("ollama") || lowered.contains("/api/chat"))
    {
        return Some((
            "Ollama Model Missing".to_string(),
            format!(
                "Your active Ollama model is missing locally.\n\n\
Model: `{model_name}`\n\n\
Run:\n\
- `/ollama pull {model_name}`\n\
- `/ollama list-models`\n\
- `/switch` (reselect Ollama model if needed)"
            ),
        ));
    }

    None
}

pub(crate) fn onboarding_usage_text() -> &'static str {
    "Usage: /onboarding\n\
       /onboarding start\n\
       /onboarding next\n\
       /onboarding prev\n\
       /onboarding <step-number>\n\
       /onboarding show\n\
       /onboarding exit"
}

pub(crate) fn format_single_service_payload(payload: &Value) -> String {
    let service_name = payload
        .get("service")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown");
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let managed = payload
        .get("managed")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let external = payload
        .get("external")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let created = payload
        .get("created")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let stopped = payload
        .get("stopped")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    let mut lines = vec![format!("**Service:** `{service_name}`")];
    if running {
        if external {
            lines.push("- Status: running (external)".to_string());
        } else if managed {
            lines.push("- Status: running (managed)".to_string());
        } else {
            lines.push("- Status: running".to_string());
        }
    } else {
        lines.push("- Status: stopped".to_string());
    }

    if created {
        lines.push("- Action: started in this command".to_string());
    }
    if stopped {
        lines.push("- Action: stopped in this command".to_string());
    }

    if let Some(pid) = payload.get("pid").and_then(|v| v.as_u64()) {
        lines.push(format!("- PID: `{pid}`"));
    }
    if let Some(command) = payload.get("command").and_then(|v| v.as_str()) {
        if !command.is_empty() {
            lines.push(format!("- Command: `{command}`"));
        }
    }
    if let Some(available) = payload.get("available").and_then(|v| v.as_bool()) {
        lines.push(format!(
            "- Executable: {}",
            if available { "found" } else { "not found" }
        ));
    }
    if let Some(executable) = payload.get("executable").and_then(|v| v.as_str()) {
        if !executable.is_empty() {
            lines.push(format!("- Executable path: `{executable}`"));
        }
    }
    if let Some(cwd) = payload.get("cwd").and_then(|v| v.as_str()) {
        if !cwd.is_empty() {
            lines.push(format!("- CWD: `{cwd}`"));
        }
    }
    if let Some(started_at) = payload.get("startedAt").and_then(|v| v.as_str()) {
        if !started_at.is_empty() {
            lines.push(format!("- Started: `{started_at}`"));
        }
    }
    if let Some(exit_code) = payload.get("exitCode").and_then(|v| v.as_i64()) {
        lines.push(format!("- Last exit code: `{exit_code}`"));
    }
    if let Some(log_path) = payload.get("logPath").and_then(|v| v.as_str()) {
        if !log_path.is_empty() {
            lines.push(format!("- Logs: `{log_path}`"));
        }
    }

    if service_name == "ollama" {
        let available = payload
            .get("available")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);
        if let Some(base_url) = payload.get("baseUrl").and_then(|v| v.as_str()) {
            if !base_url.is_empty() {
                lines.push(format!("- Base URL: `{base_url}`"));
            }
        }
        if let Some(healthy) = payload.get("healthy").and_then(|v| v.as_bool()) {
            lines.push(format!(
                "- Health: {}",
                if healthy { "reachable" } else { "unreachable" }
            ));
        }
        if !available {
            lines.push(
                "- Install Ollama or expose it in PATH. You can also set `OLLAMA_BIN=/absolute/path/to/ollama`."
                    .to_string(),
            );
        }
        if !running {
            lines.push("- Start with `/ollama start`.".to_string());
        }
    }

    if let Some(message) = payload.get("message").and_then(|v| v.as_str()) {
        if !message.is_empty() {
            lines.push(String::new());
            lines.push(message.to_string());
        }
    }

    lines.join("\n")
}

pub(crate) fn format_service_status_payload(payload: &Value) -> String {
    if let Some(services) = payload.get("services").and_then(|v| v.as_array()) {
        if services.is_empty() {
            return "No managed services found.\nUse `/service start <name> <command...>`."
                .to_string();
        }

        let mut lines = vec!["**Services:**".to_string(), String::new()];
        for service in services {
            let name = service
                .get("service")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let running = service
                .get("running")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let external = service
                .get("external")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let marker = if running { "✓" } else { "✗" };
            let state = if running { "running" } else { "stopped" };
            let scope = if external {
                "external"
            } else if service
                .get("managed")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                "managed"
            } else {
                "unmanaged"
            };
            let available = service
                .get("available")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            let availability = if available {
                ""
            } else {
                " [missing executable]"
            };
            lines.push(format!(
                "- {marker} `{name}`: {state} ({scope}){availability}"
            ));
        }
        lines.push(String::new());
        lines.push("Use `/service status <name>` for details.".to_string());
        return lines.join("\n");
    }

    format_single_service_payload(payload)
}

pub(crate) fn parse_value_literal(raw: &str) -> Value {
    let lower = raw.trim().to_lowercase();
    match lower.as_str() {
        "true" | "on" | "yes" | "enabled" => return Value::Bool(true),
        "false" | "off" | "no" | "disabled" => return Value::Bool(false),
        _ => {}
    }

    if let Ok(n) = raw.parse::<i64>() {
        return Value::Number(serde_json::Number::from(n));
    }
    if let Ok(f) = raw.parse::<f64>() {
        if let Some(num) = serde_json::Number::from_f64(f) {
            return Value::Number(num);
        }
    }
    if (raw.starts_with('{') && raw.ends_with('}')) || (raw.starts_with('[') && raw.ends_with(']'))
    {
        if let Ok(parsed) = serde_json::from_str::<Value>(raw) {
            return parsed;
        }
    }

    Value::String(raw.to_string())
}
