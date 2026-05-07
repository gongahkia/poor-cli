//! Persistent Git worktree metadata and per-worktree sessions.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::config::WokConfig;
use crate::session::{load_session, save_session, SessionError, WorkspaceSessionState};

/// One Wok-managed or externally discovered Git worktree.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorktreeRecord {
    /// Stable record id derived from the canonical worktree path.
    pub id: String,
    /// User-facing display name.
    pub name: String,
    /// Worktree root path.
    pub path: PathBuf,
    /// Attached branch name, when Git reports one.
    pub branch: Option<String>,
    /// Source marker: `primary`, `wok`, or `external`.
    pub source: String,
    /// Whether Wok created and therefore may delete this branch by request.
    #[serde(default)]
    pub owns_branch: bool,
    /// Whether this is the primary repository worktree.
    #[serde(default)]
    pub is_primary: bool,
    /// Creation timestamp in Unix milliseconds.
    #[serde(default)]
    pub created_at: u64,
}

/// Persisted worktree manifest.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorktreeManifest {
    /// Manifest schema version.
    #[serde(default = "default_manifest_schema_version")]
    pub schema_version: u32,
    /// Stable repo key derived from canonical Git common-dir.
    pub repo_key: String,
    /// Known worktrees for the repository.
    #[serde(default)]
    pub worktrees: Vec<WorktreeRecord>,
    /// Active worktree id for this repository.
    #[serde(default)]
    pub active_id: Option<String>,
}

/// Worktree removal policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RemoveWorktreeOptions {
    /// Allow removing protected entries.
    pub force: bool,
    /// Delete the owned branch after the worktree is removed.
    pub delete_branch: bool,
}

/// Errors from persistent worktree operations.
#[derive(Debug, Error)]
pub enum WorktreeStoreError {
    /// Git command failure.
    #[error("{0}")]
    Git(#[from] wok_git::service::GitServiceError),
    /// File-system I/O failure.
    #[error("worktree store I/O error: {0}")]
    Io(#[from] std::io::Error),
    /// JSON parse/encode failure.
    #[error("worktree store parse error: {0}")]
    Json(#[from] serde_json::Error),
    /// Session load/save failure.
    #[error("{0}")]
    Session(#[from] SessionError),
    /// Requested worktree was not known.
    #[error("unknown worktree: {0}")]
    UnknownWorktree(String),
    /// Requested operation is protected by default.
    #[error("{0}")]
    Protected(String),
}

/// Repository-scoped worktree store rooted under `~/.config/wok/worktrees`.
#[derive(Debug, Clone)]
pub struct WorktreeStore {
    repo_root: PathBuf,
    repo_key: String,
    store_dir: PathBuf,
    manifest: WorktreeManifest,
}

impl WorktreeStore {
    /// Open or create the worktree store for the repository containing `cwd`.
    pub fn open(cwd: &Path) -> Result<Self, WorktreeStoreError> {
        let common_dir = wok_git::service::load_common_dir(cwd)?;
        let repo_key = hex_encode_path(&common_dir);
        let store_dir = WokConfig::config_dir().join("worktrees").join(&repo_key);
        let manifest_path = store_dir.join("worktrees.json");
        let manifest = if manifest_path.exists() {
            serde_json::from_str::<WorktreeManifest>(&std::fs::read_to_string(&manifest_path)?)?
        } else {
            WorktreeManifest {
                schema_version: default_manifest_schema_version(),
                repo_key: repo_key.clone(),
                worktrees: Vec::new(),
                active_id: None,
            }
        };
        let mut store = Self {
            repo_root: cwd.to_path_buf(),
            repo_key,
            store_dir,
            manifest,
        };
        store.refresh()?;
        Ok(store)
    }

    /// Return the stable repository key.
    pub fn repo_key(&self) -> &str {
        &self.repo_key
    }

    /// Return the current manifest.
    pub fn manifest(&self) -> &WorktreeManifest {
        &self.manifest
    }

    /// Return worktree records.
    pub fn worktrees(&self) -> &[WorktreeRecord] {
        &self.manifest.worktrees
    }

    /// Return a worktree record by id or exact path string.
    pub fn find(&self, id_or_path: &str) -> Option<&WorktreeRecord> {
        self.manifest
            .worktrees
            .iter()
            .find(|record| record.id == id_or_path || record.path == PathBuf::from(id_or_path))
    }

    /// Identify the worktree containing `cwd`.
    pub fn identify_path(&self, cwd: &Path) -> Option<&WorktreeRecord> {
        self.manifest
            .worktrees
            .iter()
            .find(|record| cwd.starts_with(&record.path))
    }

    /// Refresh records from Git while preserving Wok metadata.
    pub fn refresh(&mut self) -> Result<(), WorktreeStoreError> {
        let git_worktrees = wok_git::service::list_worktrees(&self.repo_root)?;
        let previous = self.manifest.worktrees.clone();
        let primary_path = git_worktrees
            .first()
            .map(|worktree| canonical_or_original(&worktree.path));
        let mut records = Vec::new();

        for git_worktree in git_worktrees {
            if git_worktree.is_prunable {
                continue;
            }
            let path = canonical_or_original(&git_worktree.path);
            let id = worktree_id_for_path(&path);
            let is_primary = primary_path
                .as_ref()
                .is_some_and(|primary| *primary == path);
            let previous_record = previous.iter().find(|record| record.id == id);
            let source = if is_primary {
                "primary".to_string()
            } else {
                previous_record
                    .map(|record| record.source.clone())
                    .unwrap_or_else(|| "external".to_string())
            };
            records.push(WorktreeRecord {
                id,
                name: previous_record
                    .map(|record| record.name.clone())
                    .unwrap_or_else(|| {
                        default_worktree_name(&path, git_worktree.branch.as_deref())
                    }),
                path,
                branch: git_worktree.branch,
                source,
                owns_branch: previous_record.is_some_and(|record| record.owns_branch),
                is_primary,
                created_at: previous_record
                    .map(|record| record.created_at)
                    .unwrap_or_else(current_unix_ms),
            });
        }

        if self
            .manifest
            .active_id
            .as_ref()
            .is_none_or(|id| !records.iter().any(|record| &record.id == id))
        {
            self.manifest.active_id = records
                .iter()
                .find(|record| record.is_primary)
                .or_else(|| records.first())
                .map(|record| record.id.clone());
        }
        self.manifest.repo_key.clone_from(&self.repo_key);
        self.manifest.worktrees = records;
        self.save_manifest()?;
        Ok(())
    }

    /// Add a Wok-owned worktree and record ownership metadata.
    pub fn add(
        &mut self,
        path: &Path,
        branch: &str,
        create_branch: bool,
    ) -> Result<WorktreeRecord, WorktreeStoreError> {
        wok_git::service::add_worktree(&self.repo_root, path, branch, create_branch)?;
        self.refresh()?;
        let id = worktree_id_for_path(&canonical_or_original(path));
        let record = self
            .manifest
            .worktrees
            .iter_mut()
            .find(|record| record.id == id)
            .ok_or_else(|| WorktreeStoreError::UnknownWorktree(id.clone()))?;
        record.source = "wok".to_string();
        record.owns_branch = create_branch;
        record.branch = Some(branch.to_string());
        record.created_at = current_unix_ms();
        let record = record.clone();
        self.save_manifest()?;
        Ok(record)
    }

    /// Remove a worktree, enforcing Wok protection rules unless forced.
    pub fn remove(
        &mut self,
        id_or_path: &str,
        options: RemoveWorktreeOptions,
    ) -> Result<WorktreeRecord, WorktreeStoreError> {
        let record = self
            .find(id_or_path)
            .cloned()
            .ok_or_else(|| WorktreeStoreError::UnknownWorktree(id_or_path.to_string()))?;
        if record.is_primary && !options.force {
            return Err(WorktreeStoreError::Protected(
                "primary worktree cannot be removed".to_string(),
            ));
        }
        if record.source != "wok" && !options.force {
            return Err(WorktreeStoreError::Protected(
                "externally managed worktree requires force".to_string(),
            ));
        }

        wok_git::service::remove_worktree(&self.repo_root, &record.path, options.force)?;
        if options.delete_branch && record.owns_branch {
            if let Some(branch) = record.branch.as_deref() {
                wok_git::service::delete_branch(&self.repo_root, branch, options.force)?;
            }
        }
        self.delete_session(&record.id).ok();
        self.refresh()?;
        Ok(record)
    }

    /// Rename a Wok metadata record.
    pub fn rename(&mut self, id_or_path: &str, name: &str) -> Result<(), WorktreeStoreError> {
        let record = self
            .manifest
            .worktrees
            .iter_mut()
            .find(|record| record.id == id_or_path || record.path == PathBuf::from(id_or_path))
            .ok_or_else(|| WorktreeStoreError::UnknownWorktree(id_or_path.to_string()))?;
        record.name = name.trim().to_string();
        self.save_manifest()?;
        Ok(())
    }

    /// Mark the active worktree id.
    pub fn set_active(&mut self, id: String) -> Result<(), WorktreeStoreError> {
        self.manifest.active_id = Some(id);
        self.save_manifest()
    }

    /// Save a workspace snapshot for a worktree id.
    pub fn save_session_for(
        &self,
        worktree_id: &str,
        state: &WorkspaceSessionState,
    ) -> Result<(), WorktreeStoreError> {
        save_session(state, &self.session_path(worktree_id))?;
        Ok(())
    }

    /// Load a workspace snapshot for a worktree id, if present.
    pub fn load_session_for(
        &self,
        worktree_id: &str,
    ) -> Result<Option<WorkspaceSessionState>, WorktreeStoreError> {
        let path = self.session_path(worktree_id);
        if !path.exists() {
            return Ok(None);
        }
        Ok(Some(load_session(&path)?))
    }

    fn delete_session(&self, worktree_id: &str) -> Result<(), std::io::Error> {
        let path = self.session_path(worktree_id);
        if path.exists() {
            std::fs::remove_file(path)?;
        }
        Ok(())
    }

    fn session_path(&self, worktree_id: &str) -> PathBuf {
        self.store_dir
            .join("sessions")
            .join(format!("{worktree_id}.json"))
    }

    fn save_manifest(&self) -> Result<(), WorktreeStoreError> {
        std::fs::create_dir_all(&self.store_dir)?;
        let path = self.store_dir.join("worktrees.json");
        let json = serde_json::to_string_pretty(&self.manifest)?;
        std::fs::write(path, json)?;
        Ok(())
    }
}

/// Return the default path for a new sibling worktree.
pub fn default_worktree_path(primary: &Path, branch: &str) -> PathBuf {
    let name = branch
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-') {
                ch
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .to_string();
    let name = if name.is_empty() { "worktree" } else { &name };
    primary
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(name)
}

fn default_manifest_schema_version() -> u32 {
    1
}

fn default_worktree_name(path: &Path, branch: Option<&str>) -> String {
    branch.map_or_else(
        || {
            path.file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("worktree")
                .to_string()
        },
        ToString::to_string,
    )
}

fn worktree_id_for_path(path: &Path) -> String {
    hex_encode_path(path)
}

fn hex_encode_path(path: &Path) -> String {
    path.to_string_lossy()
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn canonical_or_original(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn current_unix_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |duration| duration.as_millis() as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_worktree_path_sanitizes_branch_names() {
        assert_eq!(
            default_worktree_path(Path::new("/repo/main"), "feature/demo"),
            PathBuf::from("/repo/feature-demo")
        );
    }
}
