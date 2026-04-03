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
            .unwrap_or_else(|| WalkConfig::load().shell);
        info!("starting daemon session '{name}'");
        walk_app::daemon::run_daemon_with_shell(&name, &daemon_shell)?;
        return Ok(CliAction::ExitOk);
    }
    match cli.command.clone() {
        Some(CliCommand::Rpc {
            method,
            params,
            socket,
            id,
            notify,
        }) => {
            if let Some(response) =
                rpc_cli::execute_rpc_command(method, params, socket, id, notify)?
            {
                println!("{}", serde_json::to_string_pretty(&response)?);
            }
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::List) => {
            for session in walk_app::daemon::list_sessions() {
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
            walk_app::daemon::kill_session(&name)?;
            println!("terminated session '{name}'");
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Detach { name }) => {
            walk_app::daemon::detach_session(&name)?;
            println!("detached session '{name}'");
            Ok(CliAction::ExitOk)
        }
        Some(CliCommand::Attach { name }) => {
            let summary = walk_app::daemon::attach_session(&name)?;
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
