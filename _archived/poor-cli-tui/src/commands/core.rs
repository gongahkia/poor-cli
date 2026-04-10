use super::super::*;

pub(super) fn popup_title_from_command(raw: &str) -> String {
    let token = raw
        .split_whitespace()
        .next()
        .unwrap_or("/info")
        .trim_start_matches('/')
        .trim();
    if token.is_empty() {
        return "Info".to_string();
    }
    token
        .split('-')
        .map(|segment| {
            let mut chars = segment.chars();
            match chars.next() {
                Some(first) => {
                    let mut titled = first.to_uppercase().collect::<String>();
                    titled.push_str(chars.as_str());
                    titled
                }
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

pub(super) fn show_command_info_popup(app: &mut App, raw: &str, body: impl Into<String>) {
    app.open_info_popup(popup_title_from_command(raw), body.into());
}

pub(super) fn resolve_close_slash_command(raw: &str) -> Option<(String, String, String)> {
    let command_end = raw
        .char_indices()
        .find(|(_, ch)| ch.is_whitespace())
        .map(|(index, _)| index)
        .unwrap_or(raw.len());
    if command_end == 0 {
        return None;
    }
    let typed_command = &raw[..command_end];
    if input::is_known_slash_command(typed_command) {
        return None;
    }
    let resolved = input::closest_slash_command(typed_command)?;
    let rewritten = format!("{resolved}{}", &raw[command_end..]);
    Some((rewritten, typed_command.to_string(), resolved.to_string()))
}
