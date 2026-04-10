use super::*;

pub(crate) type SessionLogWriter = Arc<Mutex<fs::File>>;

#[derive(Clone)]
pub(crate) struct BackendLaunchContext {
    pub python_bin: String,
    pub cwd: Option<String>,
    pub backend_log_path: Option<String>,
    pub session_log: Option<SessionLogWriter>,
}

#[derive(Debug, Clone, Default)]
pub(crate) struct StartupSelection {
    pub provider: Option<String>,
    pub model: Option<String>,
}

#[derive(Debug, Clone)]
pub(crate) struct PreparedContextRequest {
    pub message: String,
    pub explicit_files: Vec<String>,
    pub pinned_files: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub(crate) struct FocusState {
    pub goal: String,
    pub constraints: String,
    pub definition_of_done: String,
    pub started_at: String,
    pub completed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct ProfileState {
    pub name: String,
}

#[derive(Clone, Copy)]
pub(crate) struct ManagedEnvField {
    pub label: &'static str,
    pub provider: Option<&'static str>,
    pub env_var: &'static str,
    pub default_model: &'static str,
    pub help: &'static str,
}

pub(crate) fn managed_env_fields() -> [ManagedEnvField; 4] {
    [
        ManagedEnvField {
            label: provider_catalog::display_name("gemini"),
            provider: Some("gemini"),
            env_var: provider_catalog::env_var("gemini"),
            default_model: provider_catalog::default_model("gemini"),
            help: provider_catalog::setup_help("gemini"),
        },
        ManagedEnvField {
            label: provider_catalog::display_name("openai"),
            provider: Some("openai"),
            env_var: provider_catalog::env_var("openai"),
            default_model: provider_catalog::default_model("openai"),
            help: provider_catalog::setup_help("openai"),
        },
        ManagedEnvField {
            label: provider_catalog::display_name("anthropic"),
            provider: Some("anthropic"),
            env_var: provider_catalog::env_var("anthropic"),
            default_model: provider_catalog::default_model("anthropic"),
            help: provider_catalog::setup_help("anthropic"),
        },
        ManagedEnvField {
            label: "Brave",
            provider: None,
            env_var: "BRAVE_SEARCH_API_KEY",
            default_model: "",
            help: "Optional. Enables Brave-backed web search tooling when configured.",
        },
    ]
}

pub(crate) fn unix_ts_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

pub(crate) fn setup_session_logs(cwd: &str) -> (Option<SessionLogWriter>, Option<PathBuf>, Option<PathBuf>) {
    let logs_dir = Path::new(cwd).join(".poor-cli").join("logs");
    if fs::create_dir_all(&logs_dir).is_err() {
        return (None, None, None);
    }

    let session_id = format!("{}-{}", unix_ts_millis(), std::process::id());
    let tui_log_path = logs_dir.join(format!("tui-{session_id}.log"));
    let backend_log_path = logs_dir.join(format!("backend-{session_id}.log"));

    let writer = match OpenOptions::new()
        .create(true)
        .append(true)
        .open(&tui_log_path)
    {
        Ok(file) => Some(Arc::new(Mutex::new(file))),
        Err(_) => None,
    };

    // best-effort touch so the backend log path always exists for discovery.
    let _ = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&backend_log_path);

    (writer, Some(tui_log_path), Some(backend_log_path))
}

pub(crate) fn write_session_log(log_writer: Option<&SessionLogWriter>, message: &str) {
    let Some(writer) = log_writer else {
        return;
    };
    let mut guard = match writer.lock() {
        Ok(g) => g,
        Err(_) => return,
    };
    let _ = writeln!(&mut *guard, "{} {}", unix_ts_millis(), message);
    let _ = guard.flush();
}

pub(crate) fn chat_display_kind(display_message: &str) -> String {
    let trimmed = display_message.trim();
    if trimmed.starts_with('/') {
        let command = trimmed
            .split_whitespace()
            .next()
            .unwrap_or("/unknown")
            .trim_start_matches('/');
        if command.is_empty() {
            "slash:unknown".to_string()
        } else {
            format!("slash:{command}")
        }
    } else if trimmed.starts_with('!') {
        "bang".to_string()
    } else {
        "chat".to_string()
    }
}
