//! Blocking subprocess wrapper.

use std::ffi::{OsStr, OsString};
use std::path::Path;
use std::process::{Child, Command, Stdio};

use tracing::debug;

use crate::ProcessError;

/// Captured output of a finished subprocess.
#[derive(Debug, Clone)]
pub struct Output {
    /// Exit status as a string ("exit code 0", "signal 9", ...).
    pub status: String,
    /// Captured stdout bytes.
    pub stdout: Vec<u8>,
    /// Captured stderr bytes.
    pub stderr: Vec<u8>,
}

/// Builder for a child process invocation.
///
/// Mirrors a thin subset of `std::process::Command` so call sites do not need
/// to import `std::process` directly.
#[derive(Debug)]
pub struct Cmd {
    program: OsString,
    args: Vec<OsString>,
    envs: Vec<(OsString, OsString)>,
    cwd: Option<OsString>,
    stdin: Option<Stdio>,
    stdout: Option<Stdio>,
    stderr: Option<Stdio>,
    clear_env: bool,
}

impl Cmd {
    /// Build a new command for `program`.
    pub fn new(program: impl AsRef<OsStr>) -> Self {
        Self {
            program: program.as_ref().to_os_string(),
            args: Vec::new(),
            envs: Vec::new(),
            cwd: None,
            stdin: None,
            stdout: None,
            stderr: None,
            clear_env: false,
        }
    }

    /// Append a single argument.
    pub fn arg(mut self, arg: impl AsRef<OsStr>) -> Self {
        self.args.push(arg.as_ref().to_os_string());
        self
    }

    /// Append multiple arguments.
    pub fn args<I, S>(mut self, args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        for a in args {
            self.args.push(a.as_ref().to_os_string());
        }
        self
    }

    /// Set an environment variable.
    pub fn env(mut self, key: impl AsRef<OsStr>, val: impl AsRef<OsStr>) -> Self {
        self.envs
            .push((key.as_ref().to_os_string(), val.as_ref().to_os_string()));
        self
    }

    /// Clear inherited environment before applying `env(...)` entries.
    pub fn env_clear(mut self) -> Self {
        self.clear_env = true;
        self
    }

    /// Set the working directory.
    pub fn cwd(mut self, dir: impl AsRef<Path>) -> Self {
        self.cwd = Some(dir.as_ref().as_os_str().to_os_string());
        self
    }

    /// Set stdin to piped/null/inherited.
    pub fn stdin(mut self, s: Stdio) -> Self {
        self.stdin = Some(s);
        self
    }

    /// Set stdout to piped/null/inherited.
    pub fn stdout(mut self, s: Stdio) -> Self {
        self.stdout = Some(s);
        self
    }

    /// Set stderr to piped/null/inherited.
    pub fn stderr(mut self, s: Stdio) -> Self {
        self.stderr = Some(s);
        self
    }

    /// Consume the builder and return the underlying [`std::process::Command`].
    ///
    /// Use this when you need streaming stdio (piped stdin/stdout) and intend
    /// to manage the [`Child`] lifetime manually.
    pub fn into_std(self) -> Command {
        self.into_command()
    }

    fn into_command(self) -> Command {
        let mut cmd = Command::new(&self.program);
        if self.clear_env {
            cmd.env_clear();
        }
        for (k, v) in self.envs {
            cmd.env(k, v);
        }
        for a in self.args {
            cmd.arg(a);
        }
        if let Some(cwd) = self.cwd {
            cmd.current_dir(cwd);
        }
        if let Some(s) = self.stdin {
            cmd.stdin(s);
        }
        if let Some(s) = self.stdout {
            cmd.stdout(s);
        }
        if let Some(s) = self.stderr {
            cmd.stderr(s);
        }
        cmd
    }

    fn program_label(&self) -> String {
        self.program.to_string_lossy().into_owned()
    }
}

/// Run `cmd` to completion, capturing stdout+stderr. Errors on non-zero exit.
pub fn run(cmd: Cmd) -> Result<Output, ProcessError> {
    run_with(cmd, true)
}

/// Run `cmd` to completion. If `error_on_failure` is false, returns `Output`
/// for any exit status (caller decides what to do with non-zero).
pub fn run_with(cmd: Cmd, error_on_failure: bool) -> Result<Output, ProcessError> {
    let program = cmd.program_label();
    debug!(program = %program, "wok-process: run");
    let mut command = cmd.into_command();
    let out = command.output().map_err(|source| ProcessError::Spawn {
        program: program.clone(),
        source,
    })?;
    let status_str = format_status(&out.status);
    if !out.status.success() && error_on_failure {
        return Err(ProcessError::NonZeroExit {
            program,
            status: status_str,
            stdout: out.stdout,
            stderr: out.stderr,
        });
    }
    Ok(Output {
        status: status_str,
        stdout: out.stdout,
        stderr: out.stderr,
    })
}

/// Spawn `cmd` detached: stdin/stdout/stderr → null, no wait. Returns the [`Child`]
/// so the caller can drop it (resources released) or call `wait` / `kill`.
pub fn spawn_detached(cmd: Cmd) -> Result<Child, ProcessError> {
    let program = cmd.program_label();
    let mut command = cmd
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .into_command();
    command
        .spawn()
        .map_err(|source| ProcessError::Spawn { program, source })
}

/// Build a cross-platform shell command running `line`.
///
/// On Unix: `sh -lc "line"`. On Windows: `cmd /C line`.
pub fn sh(line: impl AsRef<OsStr>) -> Cmd {
    let line = line.as_ref().to_os_string();
    #[cfg(windows)]
    {
        Cmd::new("cmd").arg("/C").arg(line)
    }
    #[cfg(not(windows))]
    {
        Cmd::new("sh").arg("-lc").arg(line)
    }
}

#[cfg(unix)]
fn format_status(status: &std::process::ExitStatus) -> String {
    use std::os::unix::process::ExitStatusExt;
    if let Some(code) = status.code() {
        format!("exit code {code}")
    } else if let Some(sig) = status.signal() {
        format!("signal {sig}")
    } else {
        format!("{status}")
    }
}

#[cfg(not(unix))]
fn format_status(status: &std::process::ExitStatus) -> String {
    match status.code() {
        Some(code) => format!("exit code {code}"),
        None => format!("{status}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_captures_stdout() {
        let out = run(sh("echo hello")).expect("echo runs");
        assert_eq!(String::from_utf8_lossy(&out.stdout).trim(), "hello");
    }

    #[test]
    fn run_errors_on_nonzero_by_default() {
        let err = run(sh("exit 7")).unwrap_err();
        match err {
            ProcessError::NonZeroExit { status, .. } => {
                assert!(status.contains('7'), "status was {status}");
            }
            other => panic!("unexpected: {other:?}"),
        }
    }

    #[test]
    fn run_with_swallows_nonzero() {
        let out = run_with(sh("exit 3"), false).expect("non-erroring run");
        assert!(out.status.contains('3'));
    }

    #[test]
    fn spawn_detached_returns_child() {
        // `true` exits immediately on Unix; on Windows, use cmd /C exit.
        #[cfg(unix)]
        let child = spawn_detached(Cmd::new("true")).expect("spawn true");
        #[cfg(windows)]
        let child = spawn_detached(Cmd::new("cmd").args(["/C", "exit"])).expect("spawn cmd");
        drop(child);
    }

    #[test]
    fn missing_program_maps_to_spawn_error() {
        let err = run(Cmd::new("definitely-not-a-real-binary-xyz")).unwrap_err();
        match err {
            ProcessError::Spawn { program, .. } => {
                assert!(program.contains("definitely-not-a-real-binary-xyz"));
            }
            other => panic!("unexpected: {other:?}"),
        }
    }

    #[test]
    fn env_propagates() {
        let out = run(sh("printf %s \"$WOK_PROC_TEST\"").env("WOK_PROC_TEST", "hi"))
            .expect("env propagates");
        assert_eq!(String::from_utf8_lossy(&out.stdout), "hi");
    }
}
