use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::{Duration, UNIX_EPOCH};

use crate::helpers::{detect_project_traits, first_line, should_skip_dir, truncate_block};

#[derive(Default)]
pub struct WatchState {
    pub stop_flag: Option<Arc<AtomicBool>>,
    pub handle: Option<thread::JoinHandle<()>>,
    pub directory: Option<String>,
}

impl WatchState {
    pub fn is_running(&self) -> bool {
        self.handle.is_some()
    }
    pub fn stop(&mut self) {
        if let Some(flag) = &self.stop_flag {
            flag.store(true, Ordering::SeqCst);
        }
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
        self.stop_flag = None;
        self.directory = None;
    }
}

#[derive(Default)]
pub struct QaWatchState {
    pub stop_flag: Option<Arc<AtomicBool>>,
    pub handle: Option<thread::JoinHandle<()>>,
    pub directory: Option<String>,
    pub command: Option<String>,
}

impl QaWatchState {
    pub fn is_running(&self) -> bool {
        self.handle.is_some()
    }
    pub fn stop(&mut self) {
        if let Some(flag) = &self.stop_flag {
            flag.store(true, Ordering::SeqCst);
        }
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
        self.stop_flag = None;
        self.directory = None;
        self.command = None;
    }
}

/// Message type used by watcher to communicate back to main loop.
/// We accept a generic sender that can send these variants.
pub enum WatchMsg {
    System(String),
    AutomationPrompt { display: String, prompt: String },
    Error(String),
}

pub fn spawn_watch_worker(
    directory: String,
    prompt: String,
    tx: mpsc::Sender<WatchMsg>,
    stop: Arc<AtomicBool>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let root = PathBuf::from(&directory);
        let mut previous = snapshot_directory(&root);

        while !stop.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_secs(2));
            if stop.load(Ordering::SeqCst) {
                break;
            }

            let current = snapshot_directory(&root);
            let changed = detect_changed_files(&previous, &current);
            previous = current;

            if changed.is_empty() {
                continue;
            }

            let preview = changed
                .iter()
                .take(8)
                .map(|p| format!("- {p}"))
                .collect::<Vec<_>>()
                .join("\n");
            let _ = tx.send(WatchMsg::System(format!(
                "Watch mode detected {} changed file(s) in `{directory}`:\n{preview}",
                changed.len()
            )));

            let _ = tx.send(WatchMsg::AutomationPrompt {
                display: format!(
                    "[watch] analyze {} changed file(s) in {}",
                    changed.len(),
                    directory
                ),
                prompt: build_watch_prompt(&changed, &prompt),
            });
        }
    })
}

pub fn default_qa_command_for_workspace(root: &Path) -> String {
    let traits = detect_project_traits(root);
    if traits.contains(&"rust") && traits.contains(&"python") {
        return "cargo test -q && pytest -q".to_string();
    }
    if traits.contains(&"rust") {
        return "cargo test -q".to_string();
    }
    if traits.contains(&"python") {
        return "pytest -q".to_string();
    }
    if traits.contains(&"javascript") {
        return "npm test -- --watch=false".to_string();
    }
    "make test".to_string()
}

pub fn run_qa_command(directory: &str, command: &str) -> Result<(i32, String), String> {
    let output = Command::new("sh")
        .arg("-lc")
        .arg(command)
        .current_dir(directory)
        .output()
        .map_err(|e| format!("Failed to run QA command `{command}`: {e}"))?;

    let exit_code = output.status.code().unwrap_or(1);
    let combined = format!(
        "{}{}{}",
        String::from_utf8_lossy(&output.stdout),
        if output.stdout.is_empty() || output.stderr.is_empty() {
            ""
        } else {
            "\n"
        },
        String::from_utf8_lossy(&output.stderr)
    );
    Ok((exit_code, truncate_block(&combined, 2800)))
}

pub fn spawn_qa_watch_worker(
    directory: String,
    command: String,
    tx: mpsc::Sender<WatchMsg>,
    stop: Arc<AtomicBool>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let root = PathBuf::from(&directory);
        let mut previous = snapshot_directory(&root);
        let mut last_success: Option<bool> = None;
        let mut last_signature = String::new();

        while !stop.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_secs(2));
            if stop.load(Ordering::SeqCst) {
                break;
            }

            let current = snapshot_directory(&root);
            let changed = detect_changed_files(&previous, &current);
            previous = current;

            if changed.is_empty() {
                continue;
            }

            let change_preview = changed
                .iter()
                .take(6)
                .map(|path| format!("- {path}"))
                .collect::<Vec<_>>()
                .join("\n");

            match run_qa_command(&directory, &command) {
                Ok((exit_code, output)) => {
                    let success = exit_code == 0;
                    let signature = format!("{success}:{}", first_line(&output));
                    let changed_state = last_success != Some(success);
                    let changed_signature = signature != last_signature;
                    last_success = Some(success);
                    last_signature = signature;

                    if !changed_state && !changed_signature {
                        continue;
                    }

                    let status = if success { "PASS" } else { "FAIL" };
                    let mut lines = vec![
                        format!("**QA Watch** `{status}` (`{command}`)"),
                        format!("- Directory: `{directory}`"),
                        format!("- Changed files: {}", changed.len()),
                        change_preview,
                    ];

                    if !output.trim().is_empty() {
                        lines.push(String::new());
                        lines.push("```text".to_string());
                        lines.push(output.clone());
                        lines.push("```".to_string());
                    }
                    let _ = tx.send(WatchMsg::System(lines.join("\n")));
                    let _ = tx.send(WatchMsg::AutomationPrompt {
                        display: format!(
                            "[qa] inspect {} result for {}",
                            status.to_ascii_lowercase(),
                            directory
                        ),
                        prompt: build_qa_watch_prompt(
                            &directory, &command, &changed, &output, success,
                        ),
                    });
                }
                Err(error) => {
                    let _ = tx.send(WatchMsg::Error(format!("QA watch failed: {error}")));
                    break;
                }
            }
        }
    })
}

pub fn snapshot_directory(root: &Path) -> HashMap<String, u64> {
    let mut snapshot = HashMap::new();
    let mut stack = vec![root.to_path_buf()];

    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            let file_name = entry.file_name();
            let name = file_name.to_string_lossy();

            if path.is_dir() {
                if should_skip_dir(&name) {
                    continue;
                }
                stack.push(path);
                continue;
            }

            if !path.is_file() {
                continue;
            }

            let modified = entry
                .metadata()
                .ok()
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);

            snapshot.insert(path.to_string_lossy().to_string(), modified);
        }
    }

    snapshot
}

pub fn detect_changed_files(
    previous: &HashMap<String, u64>,
    current: &HashMap<String, u64>,
) -> Vec<String> {
    let mut changed = current
        .iter()
        .filter_map(|(path, mtime)| {
            if previous.get(path).copied() != Some(*mtime) {
                Some(path.clone())
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    changed.sort();
    changed
}

pub fn build_watch_prompt(changed: &[String], user_prompt: &str) -> String {
    let mut sections = vec![
        "The following files changed. Analyze what changed, why it matters, and any risks."
            .to_string(),
    ];

    for path in changed.iter().take(5) {
        let content = match fs::read(path) {
            Ok(bytes) => {
                if bytes.len() > 250_000 {
                    format!(
                        "(file too large to include fully: {} bytes, showing first 250000 bytes)\n{}",
                        bytes.len(),
                        String::from_utf8_lossy(&bytes[..250_000])
                    )
                } else {
                    String::from_utf8_lossy(&bytes).to_string()
                }
            }
            Err(e) => format!("(unable to read file: {e})"),
        };

        sections.push(format!(
            "File: {path}\n```\n{}\n```",
            truncate_block(&content, 4000)
        ));
    }

    sections.push(format!("User request: {user_prompt}"));
    sections.join("\n\n")
}

pub fn build_qa_watch_prompt(
    directory: &str,
    command: &str,
    changed: &[String],
    output: &str,
    success: bool,
) -> String {
    let mut sections = vec![if success {
        "QA watch ran after filesystem changes. Review the clean result, summarize residual risk, and only make changes if you see a concrete regression signal.".to_string()
    } else {
        "QA watch detected a failing validation run. Diagnose the failure, explain the likely cause, and make the smallest safe fix if the cause is clear.".to_string()
    }];

    sections.push(format!("Directory: {directory}"));
    sections.push(format!("Command: {command}"));

    if !changed.is_empty() {
        sections.push("Changed files:".to_string());
        for path in changed.iter().take(12) {
            sections.push(format!("- {path}"));
        }
    }

    if !output.trim().is_empty() {
        sections.push("Command output:".to_string());
        sections.push(format!("```text\n{}\n```", truncate_block(output, 4000)));
    }

    sections.join("\n\n")
}
