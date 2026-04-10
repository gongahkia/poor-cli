use super::*;

// ── API-key editor & .env file management ──────────────────────────

pub(crate) fn workspace_env_paths(app: &App) -> (PathBuf, PathBuf) {
    let root = if app.cwd.trim().is_empty() {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    } else {
        PathBuf::from(&app.cwd)
    };
    (root.join(".env"), root.join(".env.example"))
}

pub(crate) fn parse_env_line_key(line: &str) -> Option<String> {
    let mut trimmed = line.trim_start();
    if let Some(rest) = trimmed.strip_prefix('#') {
        trimmed = rest.trim_start();
    }
    if let Some(rest) = trimmed.strip_prefix("export ") {
        trimmed = rest.trim_start();
    }
    let (key, _) = trimmed.split_once('=')?;
    let key = key.trim();
    if key.is_empty()
        || !key.chars().enumerate().all(|(idx, ch)| {
            if idx == 0 {
                ch == '_' || ch.is_ascii_alphabetic()
            } else {
                ch == '_' || ch.is_ascii_alphanumeric()
            }
        })
    {
        return None;
    }
    Some(key.to_string())
}

pub(crate) fn parse_env_assignments(contents: &str) -> HashMap<String, String> {
    let mut values = HashMap::new();
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let mut working = trimmed;
        if let Some(rest) = working.strip_prefix("export ") {
            working = rest.trim_start();
        }
        let Some((key, raw_value)) = working.split_once('=') else {
            continue;
        };
        let key = key.trim();
        if key.is_empty() {
            continue;
        }
        let mut value = raw_value.trim().to_string();
        if value.len() >= 2 {
            let quoted = (value.starts_with('"') && value.ends_with('"'))
                || (value.starts_with('\'') && value.ends_with('\''));
            if quoted {
                value = value[1..value.len() - 1].to_string();
            }
        }
        values.insert(key.to_string(), value);
    }
    values
}

pub(crate) fn format_env_value(value: &str) -> String {
    if value.is_empty() {
        return String::new();
    }
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.' | '/' | ':' | '+'))
    {
        return value.to_string();
    }
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

pub(crate) fn update_env_file_contents(base: &str, updates: &HashMap<String, String>) -> String {
    let mut seen = HashSet::new();
    let mut rendered = Vec::new();
    let managed_env_fields = managed_env_fields();
    for line in base.lines() {
        if let Some(key) = parse_env_line_key(line) {
            if let Some(value) = updates.get(&key) {
                rendered.push(format!("{key}={}", format_env_value(value)));
                seen.insert(key);
                continue;
            }
        }
        rendered.push(line.to_string());
    }

    for spec in &managed_env_fields {
        if seen.contains(spec.env_var) {
            continue;
        }
        if let Some(value) = updates.get(spec.env_var) {
            rendered.push(format!("{}={}", spec.env_var, format_env_value(value)));
        }
    }

    let mut output = rendered.join("\n");
    if !output.ends_with('\n') {
        output.push('\n');
    }
    output
}

pub(crate) fn build_api_key_editor_state(
    app: &App,
    init_error: Option<&str>,
) -> Result<ApiKeyEditorState, String> {
    let (env_path, template_path) = workspace_env_paths(app);
    let env_exists = env_path.exists();

    let env_values = if env_exists {
        let content = fs::read_to_string(&env_path)
            .map_err(|e| format!("Failed to read {}: {e}", env_path.display()))?;
        parse_env_assignments(&content)
    } else {
        HashMap::new()
    };

    let mut fields = Vec::new();
    let mut selected_index = 0usize;
    let managed_env_fields = managed_env_fields();
    for (idx, spec) in managed_env_fields.iter().enumerate() {
        let value = env_values
            .get(spec.env_var)
            .cloned()
            .or_else(|| std::env::var(spec.env_var).ok())
            .unwrap_or_default();
        if spec.provider == Some(app.provider.name.as_str()) {
            selected_index = idx;
        }
        fields.push(ApiKeyEditorField {
            label: spec.label.to_string(),
            provider: spec.provider.map(str::to_string),
            env_var: spec.env_var.to_string(),
            help: spec.help.to_string(),
            value,
        });
    }

    Ok(ApiKeyEditorState {
        env_path: env_path.display().to_string(),
        template_path: template_path.display().to_string(),
        env_exists,
        selected_index,
        cursor: fields
            .get(selected_index)
            .map(|field| field.value.len())
            .unwrap_or(0),
        fields,
        status: if env_exists {
            "Edit keys and press Ctrl+S to save.".to_string()
        } else {
            "No .env found. Saving will create one from .env.example.".to_string()
        },
        error: String::new(),
        init_error: init_error.unwrap_or("").to_string(),
        target_provider: app.provider.name.clone(),
        target_model: app.provider.model.clone(),
    })
}

pub(crate) fn open_api_key_setup_editor(app: &mut App, init_error: Option<&str>) -> Result<(), String> {
    let state = build_api_key_editor_state(app, init_error)?;
    app.open_api_key_editor(state);
    Ok(())
}

pub(crate) fn select_setup_provider_model(editor: &ApiKeyEditorState) -> (String, String) {
    let managed_env_fields = managed_env_fields();
    let active_has_key = managed_env_fields.iter().any(|spec| {
        spec.provider == Some(editor.target_provider.as_str())
            && editor
                .fields
                .iter()
                .find(|field| field.env_var == spec.env_var)
                .map(|field| !field.value.trim().is_empty())
                .unwrap_or(false)
    });

    if editor.target_provider.eq_ignore_ascii_case("ollama") || active_has_key {
        return (editor.target_provider.clone(), editor.target_model.clone());
    }

    for spec in &managed_env_fields {
        let Some(provider) = spec.provider else {
            continue;
        };
        let has_value = editor
            .fields
            .iter()
            .find(|field| field.env_var == spec.env_var)
            .map(|field| !field.value.trim().is_empty())
            .unwrap_or(false);
        if has_value {
            return (provider.to_string(), spec.default_model.to_string());
        }
    }

    (editor.target_provider.clone(), editor.target_model.clone())
}

pub(crate) fn save_api_key_editor(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<String, String> {
    let editor = app
        .api_key_editor
        .clone()
        .ok_or_else(|| "Setup editor is not open.".to_string())?;
    let env_path = PathBuf::from(&editor.env_path);
    let template_path = PathBuf::from(&editor.template_path);

    let base = if env_path.exists() {
        fs::read_to_string(&env_path)
            .map_err(|e| format!("Failed to read {}: {e}", env_path.display()))?
    } else if template_path.exists() {
        fs::read_to_string(&template_path)
            .map_err(|e| format!("Failed to read {}: {e}", template_path.display()))?
    } else {
        "# Generated by poor-cli /setup\n".to_string()
    };

    let mut updates = HashMap::new();
    for field in &editor.fields {
        updates.insert(field.env_var.clone(), field.value.trim().to_string());
    }

    let rendered = update_env_file_contents(&base, &updates);
    if let Some(parent) = env_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to prepare {}: {e}", parent.display()))?;
    }
    fs::write(&env_path, rendered)
        .map_err(|e| format!("Failed to write {}: {e}", env_path.display()))?;

    for field in &editor.fields {
        let value = field.value.trim();
        if value.is_empty() {
            std::env::remove_var(&field.env_var);
        } else {
            std::env::set_var(&field.env_var, value);
        }
    }

    for field in &editor.fields {
        if let Some(provider) = field.provider.as_deref() {
            let value = field.value.trim();
            if value.is_empty() {
                continue;
            }
            rpc_set_api_key_blocking(rpc_cmd_tx, provider, value, true).map_err(|e| {
                format!(
                    "Saved .env but failed to store `{}` in backend: {e}",
                    field.env_var
                )
            })?;
        }
    }

    let (provider, model) = select_setup_provider_model(&editor);
    let init = rpc_initialize_blocking(rpc_cmd_tx, Some(&provider), Some(&model))
        .map_err(|e| format!("Saved .env but backend initialization still failed: {e}"))?;
    tx.send(server_msg_from_init_result(
        init,
        &Some(provider.clone()),
        &Some(model.clone()),
    ))
    .map_err(|e| format!("Saved .env but failed to apply initialization result: {e}"))?;

    Ok(format!(
        "Saved {} \u{2014} now using **{}/{}**",
        env_path.display(), provider, model
    ))
}

pub(crate) fn should_offer_api_key_setup(message: &str) -> bool {
    let lowered = message.to_ascii_lowercase();
    lowered.contains("api key")
        || lowered.contains("set environment variable")
        || lowered.contains("no api key found")
        || lowered.contains("initialization failed")
        || lowered.contains("auth")
}
