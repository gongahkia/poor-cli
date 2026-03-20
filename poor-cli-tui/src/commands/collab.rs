use super::super::*;

pub(super) fn current_multiplayer_room(app: &App) -> Option<&str> {
    if app.multiplayer.room.is_empty() {
        None
    } else {
        Some(app.multiplayer.room.as_str())
    }
}

pub(super) fn first_host_room_name(payload: &Value, preferred_room: Option<&str>) -> Option<String> {
    let rooms = payload.get("rooms").and_then(|value| value.as_array())?;
    if let Some(preferred) = preferred_room.filter(|value| !value.is_empty()) {
        for room in rooms {
            if room.get("name").and_then(|value| value.as_str()) == Some(preferred) {
                return Some(preferred.to_string());
            }
        }
    }
    rooms.iter().find_map(|room| {
        room.get("name")
            .and_then(|value| value.as_str())
            .map(|value| value.to_string())
    })
}

pub(super) fn room_field<'a>(payload: &'a Value, room_name: &str, field: &str) -> Option<&'a str> {
    payload
        .get("rooms")
        .and_then(|value| value.as_array())
        .and_then(|rooms| {
            rooms.iter().find(|room| {
                room.get("name")
                    .and_then(|value| value.as_str())
                    .is_some_and(|name| name == room_name)
            })
        })
        .and_then(|room| room.get(field))
        .and_then(|value| value.as_str())
}

pub(super) fn collab_share_role(raw: &str) -> Option<&'static str> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "driver" | "prompter" => Some("prompter"),
        "viewer" | "navigator" | "reviewer" => Some("viewer"),
        _ => None,
    }
}

pub(super) fn collab_usage_text() -> &'static str {
    "Usage: /collab start <pair|mob|review>\n\
       /collab join [invite-code]\n\
       /collab status\n\
       /collab summary\n\
       /collab members\n\
       /collab share [driver|viewer]\n\
       /collab handoff [next|#N|@name]\n\
       /collab remove [#N|@name|connection-id]\n\
       /collab lobby <on|off>\n\
       /collab approve [#N|@name]\n\
       /collab deny [#N|@name]\n\
       /collab agenda add <text>\n\
       /collab agenda list\n\
       /collab agenda done <item-id>\n\
       /collab hand raise\n\
       /collab hand lower\n\n\
All collaboration features are accessed through /collab subcommands."
}

pub(crate) fn format_collab_summary_payload(payload: &Value) -> String {
    let collab = payload.get("collaboration").unwrap_or(payload);
    let running = collab
        .get("running")
        .and_then(|value| value.as_bool())
        .unwrap_or(false);
    let role = collab
        .get("role")
        .and_then(|value| value.as_str())
        .unwrap_or("solo");
    let room = collab
        .get("room")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    let member_count = collab
        .get("memberCount")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let summary = collab
        .get("summary")
        .and_then(|value| value.as_str())
        .unwrap_or("No collaboration summary available.");
    let health = collab
        .get("connectionHealth")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let queue_depth = collab
        .pointer("/queueState/depth")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let hands_raised = collab
        .pointer("/queueState/handsRaised")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let mut lines = vec![
        "**Collaboration Summary**".to_string(),
        format!("- Running: `{running}`"),
        format!("- Role: `{role}`"),
        format!("- Room: `{}`", if room.is_empty() { "-" } else { room }),
        format!("- Members: {member_count}"),
        format!("- Queue depth: {queue_depth}"),
        format!("- Hands raised: {hands_raised}"),
        format!("- Connection health: `{health}`"),
        format!("- Summary: {summary}"),
    ];
    if let Some(signaling_url) = collab.get("signalingUrl").and_then(|value| value.as_str()) {
        if !signaling_url.is_empty() {
            lines.push(format!("- Signaling: `{signaling_url}`"));
        }
    }
    lines.join("\n")
}
