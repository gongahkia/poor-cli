use super::*;

pub(crate) enum CliAction {
    ContinueToWindow { attached_session: Option<String> },
    ExitOk,
}

pub(crate) fn dispatch_cli_command(cli: &Cli) -> Result<CliAction, Box<dyn Error>> {
    if let Some(name) = cli.daemon.clone() {
        let daemon_shell = cli
            .shell
            .as_deref()
            .map(parse_shell_type)
            .unwrap_or_else(|| WokConfig::load().shell);
        info!("starting daemon session '{name}'");
        wok_app::daemon::run_daemon_with_shell(&name, &daemon_shell)?;
        return Ok(CliAction::ExitOk);
    }
    match cli.command.clone() {
        Some(CliCommand::Init { overwrite }) => {
            setup_ops::run_init(overwrite)?;
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Doctor { json }) => {
            setup_ops::run_doctor(json)?;
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Reset { scope, yes }) => {
            setup_ops::run_reset(scope, yes)?;
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::BugReport { output }) => {
            setup_ops::run_bug_report(output)?;
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Replay { file, speed }) => {
            run_wokcast_replay(&file, speed)?;
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Onboard {
            shell,
            no_install,
            overwrite,
        }) => {
            setup_ops::run_onboard(shell.as_deref(), !no_install, overwrite)?;
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Shell { command }) => {
            match command {
                ShellCommand::Install { shell, overwrite } => {
                    setup_ops::run_shell_install(shell.as_deref(), overwrite)?;
                }
                ShellCommand::Rollback { shell, yes } => {
                    setup_ops::run_shell_rollback(shell.as_deref(), yes)?;
                }
            }
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Workspace { command }) => {
            match command {
                WorkspaceCommand::Save {
                    name,
                    socket,
                    token,
                } => {
                    run_workspace_action(&format!("save_session:{name}"), socket, token)?;
                    println!("saved workspace '{name}'");
                }
                WorkspaceCommand::Load {
                    name,
                    socket,
                    token,
                } => {
                    run_workspace_action(&format!("load_session:{name}"), socket, token)?;
                    println!("loaded workspace '{name}'");
                }
                WorkspaceCommand::List => {
                    let dir = WokConfig::config_dir().join("sessions");
                    if let Ok(read_dir) = std::fs::read_dir(dir) {
                        for entry in read_dir.flatten() {
                            let path = entry.path();
                            if path.extension().and_then(|ext| ext.to_str()) == Some("json") {
                                if let Some(name) = path.file_stem().and_then(|name| name.to_str())
                                {
                                    println!("{name}");
                                }
                            }
                        }
                    }
                }
            }
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Rpc {
            method,
            params,
            socket,
            token,
            id,
            notify,
        }) => {
            if let Some(response) =
                rpc_cli::execute_rpc_command(method, params, socket, token, id, notify)?
            {
                println!("{}", serde_json::to_string_pretty(&response)?);
            }
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::GitStatus {
            pane_id,
            socket,
            token,
        }) => {
            let status = rpc_cli::execute_git_status_command(pane_id, socket, token)?;
            println!("{}", serde_json::to_string_pretty(&status)?);
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::List) => {
            for session in wok_app::daemon::list_sessions() {
                println!(
                    "{} ({} pane{}, {} attached)",
                    session.name,
                    session.pane_count,
                    if session.pane_count == 1 { "" } else { "s" },
                    session.attached_clients
                );
            }
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Kill { name }) => {
            wok_app::daemon::kill_session(&name)?;
            println!("terminated session '{name}'");
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Detach { name }) => {
            wok_app::daemon::detach_session(&name)?;
            println!("detached session '{name}'");
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Attach { name }) => {
            let summary = wok_app::daemon::attach_session(&name)?;
            info!(
                "attached to session '{}' ({} pane{}, {} attached)",
                summary.name,
                summary.pane_count,
                if summary.pane_count == 1 { "" } else { "s" },
                summary.attached_clients
            );
            Ok(CliAction::ContinueToWindow {
                attached_session: Some(summary.name),
            })
        }
        None => Ok(CliAction::ContinueToWindow {
            attached_session: None,
        }),
    }
}

fn run_workspace_action(
    action: &str,
    socket: Option<String>,
    token: Option<String>,
) -> Result<(), Box<dyn Error>> {
    let response = rpc_cli::execute_rpc_command(
        "wok.run_action".to_string(),
        serde_json::json!({ "action": action }).to_string(),
        socket,
        token,
        None,
        false,
    )?
    .ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::UnexpectedEof,
            "remote control server did not return a response",
        )
    })?;
    if let Some(error) = response.get("error") {
        return Err(std::io::Error::other(format!("remote RPC error: {error}")).into());
    }
    Ok(())
}

fn run_wokcast_replay(file: &std::path::Path, speed: f64) -> Result<(), Box<dyn Error>> {
    use std::io::{stdout, Write};
    use wok_terminal::cast::{schedule, CastReader};
    let f = std::fs::File::open(file)?;
    let mut reader = CastReader::new(f);
    let plan = schedule(&mut reader, speed)?;
    let mut out = stdout().lock();
    for (delay, bytes) in plan {
        if !delay.is_zero() {
            std::thread::sleep(delay);
        }
        out.write_all(&bytes)?;
        out.flush()?;
    }
    Ok(())
}

pub(crate) fn parse_shell_type(value: &str) -> ShellType {
    if let Some(distro) = value.strip_prefix("wsl:") {
        return ShellType::Wsl(distro.to_string());
    }
    match value {
        "zsh" => ShellType::Zsh,
        "fish" => ShellType::Fish,
        "powershell" => ShellType::PowerShell,
        _ => ShellType::Bash,
    }
}
