/// Mutation review state, decision summaries, and diff chunk parsing.
use std::collections::{HashMap, HashSet};

// ── Review chunk types ──────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApprovedReviewChunk {
    pub path: String,
    pub hunk_index: usize,
}

#[derive(Debug, Clone, Default)]
pub struct MutationReviewChunk {
    pub path: String,
    pub hunk_index: usize,
    pub header: String,
    pub diff: String,
    pub selected: bool,
}

#[derive(Debug, Clone, Default)]
pub struct MutationReviewState {
    pub request_id: String,
    pub tool_name: String,
    pub operation: String,
    pub prompt_id: String,
    pub paths: Vec<String>,
    pub diff: String,
    pub checkpoint_id: Option<String>,
    pub changed: Option<bool>,
    pub message: String,
    pub selected_path_index: usize,
    pub chunks: Vec<MutationReviewChunk>,
    pub selected_chunk_index: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MutationReviewFileGroup {
    pub path: String,
    pub chunk_indexes: Vec<usize>,
    pub selected_chunks: usize,
}

impl MutationReviewFileGroup {
    pub fn total_chunks(&self) -> usize {
        self.chunk_indexes.len()
    }
    pub fn decision_state(&self) -> ReviewDecisionState {
        if self.selected_chunks == 0 {
            ReviewDecisionState::Rejected
        } else if self.selected_chunks == self.total_chunks() {
            ReviewDecisionState::Accepted
        } else {
            ReviewDecisionState::Partial
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReviewDecisionState {
    Accepted,
    Partial,
    Rejected,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewDecisionFileSummary {
    pub path: String,
    pub state: ReviewDecisionState,
    pub total_hunks: usize,
    pub accepted_hunks: Vec<usize>,
    pub rejected_hunks: Vec<usize>,
}

impl ReviewDecisionFileSummary {
    pub fn summary_line(&self) -> String {
        match self.total_hunks {
            0 => match self.state {
                ReviewDecisionState::Accepted => format!("{}: accepted", self.path),
                ReviewDecisionState::Partial => format!("{}: partial", self.path),
                ReviewDecisionState::Rejected => format!("{}: rejected", self.path),
            },
            _ => {
                let accepted = format_hunk_labels(&self.accepted_hunks);
                let rejected = format_hunk_labels(&self.rejected_hunks);
                match self.state {
                    ReviewDecisionState::Accepted => {
                        format!("{}: accepted hunks {}", self.path, accepted)
                    }
                    ReviewDecisionState::Rejected => {
                        format!("{}: rejected hunks {}", self.path, rejected)
                    }
                    ReviewDecisionState::Partial => format!(
                        "{}: accepted {}; rejected {}",
                        self.path, accepted, rejected
                    ),
                }
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewDecisionSummary {
    pub total_files: usize,
    pub accepted_files: usize,
    pub total_hunks: usize,
    pub accepted_hunks: usize,
    pub files: Vec<ReviewDecisionFileSummary>,
}

impl ReviewDecisionSummary {
    pub fn headline(&self) -> String {
        if self.total_hunks > 0 {
            if self.accepted_hunks == 0 {
                format!(
                    "Rejected all {} hunks across {} files",
                    self.total_hunks, self.total_files
                )
            } else if self.accepted_hunks == self.total_hunks {
                format!(
                    "Accepted all {} hunks across {} files",
                    self.total_hunks, self.total_files
                )
            } else {
                format!(
                    "Accepted {}/{} hunks across {}/{} files",
                    self.accepted_hunks, self.total_hunks, self.accepted_files, self.total_files
                )
            }
        } else if self.accepted_files == 0 {
            format!("Rejected all {} files", self.total_files)
        } else if self.accepted_files == self.total_files {
            format!("Accepted all {} files", self.total_files)
        } else {
            format!(
                "Accepted {}/{} files",
                self.accepted_files, self.total_files
            )
        }
    }
}

impl MutationReviewState {
    pub fn supports_chunk_approval(&self) -> bool {
        self.tool_name == "apply_patch_unified" && !self.chunks.is_empty()
    }
    pub fn selected_chunk(&self) -> Option<&MutationReviewChunk> {
        self.chunks.get(self.selected_chunk_index)
    }
    pub fn sync_selected_path_from_chunk(&mut self) {
        if let Some(chunk) = self.selected_chunk() {
            if let Some(index) = self.paths.iter().position(|path| path == &chunk.path) {
                self.selected_path_index = index;
            }
        }
    }
    pub fn approved_chunks(&self) -> Vec<ApprovedReviewChunk> {
        self.chunks
            .iter()
            .filter(|chunk| chunk.selected)
            .map(|chunk| ApprovedReviewChunk {
                path: chunk.path.clone(),
                hunk_index: chunk.hunk_index,
            })
            .collect()
    }
    pub fn file_groups(&self) -> Vec<MutationReviewFileGroup> {
        let mut groups: Vec<MutationReviewFileGroup> = Vec::new();
        let mut positions: HashMap<&str, usize> = HashMap::new();
        for (index, chunk) in self.chunks.iter().enumerate() {
            if let Some(position) = positions.get(chunk.path.as_str()).copied() {
                let group = &mut groups[position];
                group.chunk_indexes.push(index);
                if chunk.selected {
                    group.selected_chunks += 1;
                }
            } else {
                positions.insert(chunk.path.as_str(), groups.len());
                groups.push(MutationReviewFileGroup {
                    path: chunk.path.clone(),
                    chunk_indexes: vec![index],
                    selected_chunks: usize::from(chunk.selected),
                });
            }
        }
        groups
    }
    pub fn selected_file_group_index(&self) -> Option<usize> {
        let groups = self.file_groups();
        groups.iter().enumerate().find_map(|(group_index, group)| {
            group
                .chunk_indexes
                .contains(&self.selected_chunk_index)
                .then_some(group_index)
        })
    }
    pub fn jump_to_file_group(&mut self, reverse: bool) -> bool {
        let groups = self.file_groups();
        if groups.is_empty() {
            return false;
        }
        let current = self.selected_file_group_index().unwrap_or(0);
        let target = if reverse {
            current.saturating_sub(1)
        } else if current + 1 < groups.len() {
            current + 1
        } else {
            current
        };
        if target == current {
            return false;
        }
        if let Some(next_chunk_index) = groups[target].chunk_indexes.first().copied() {
            self.selected_chunk_index = next_chunk_index;
            self.sync_selected_path_from_chunk();
            return true;
        }
        false
    }
    pub fn set_current_file_group_selection(&mut self, selected: bool) -> Option<String> {
        let groups = self.file_groups();
        let group_index = self.selected_file_group_index()?;
        let group = groups.get(group_index)?;
        for chunk_index in &group.chunk_indexes {
            if let Some(chunk) = self.chunks.get_mut(*chunk_index) {
                chunk.selected = selected;
            }
        }
        Some(group.path.clone())
    }
    pub fn build_decision_summary(
        &self,
        allowed: bool,
        approved_paths: &[String],
        approved_chunks: &[ApprovedReviewChunk],
    ) -> ReviewDecisionSummary {
        if self.supports_chunk_approval() {
            return self.build_chunk_decision_summary(allowed, approved_paths, approved_chunks);
        }
        self.build_path_decision_summary(allowed, approved_paths)
    }
    fn build_chunk_decision_summary(
        &self,
        allowed: bool,
        approved_paths: &[String],
        approved_chunks: &[ApprovedReviewChunk],
    ) -> ReviewDecisionSummary {
        let accepted_keys = if !allowed {
            HashSet::new()
        } else if !approved_chunks.is_empty() {
            approved_chunks
                .iter()
                .map(|chunk| (chunk.path.clone(), chunk.hunk_index))
                .collect::<HashSet<_>>()
        } else if !approved_paths.is_empty() {
            self.chunks
                .iter()
                .filter(|chunk| approved_paths.iter().any(|path| path == &chunk.path))
                .map(|chunk| (chunk.path.clone(), chunk.hunk_index))
                .collect::<HashSet<_>>()
        } else {
            self.chunks
                .iter()
                .map(|chunk| (chunk.path.clone(), chunk.hunk_index))
                .collect::<HashSet<_>>()
        };
        let groups = self.file_groups();
        let files = groups
            .into_iter()
            .map(|group| {
                let mut accepted_hunks = Vec::new();
                let mut rejected_hunks = Vec::new();
                for chunk_index in group.chunk_indexes {
                    if let Some(chunk) = self.chunks.get(chunk_index) {
                        if accepted_keys.contains(&(chunk.path.clone(), chunk.hunk_index)) {
                            accepted_hunks.push(chunk.hunk_index);
                        } else {
                            rejected_hunks.push(chunk.hunk_index);
                        }
                    }
                }
                let state = if accepted_hunks.is_empty() {
                    ReviewDecisionState::Rejected
                } else if rejected_hunks.is_empty() {
                    ReviewDecisionState::Accepted
                } else {
                    ReviewDecisionState::Partial
                };
                ReviewDecisionFileSummary {
                    path: group.path,
                    state,
                    total_hunks: accepted_hunks.len() + rejected_hunks.len(),
                    accepted_hunks,
                    rejected_hunks,
                }
            })
            .collect::<Vec<_>>();
        ReviewDecisionSummary {
            total_files: files.len(),
            accepted_files: files
                .iter()
                .filter(|file| file.state != ReviewDecisionState::Rejected)
                .count(),
            total_hunks: files.iter().map(|file| file.total_hunks).sum(),
            accepted_hunks: files.iter().map(|file| file.accepted_hunks.len()).sum(),
            files,
        }
    }
    fn build_path_decision_summary(
        &self,
        allowed: bool,
        approved_paths: &[String],
    ) -> ReviewDecisionSummary {
        let paths = if self.paths.is_empty() {
            vec![self.tool_name.clone()]
        } else {
            self.paths.clone()
        };
        let files = paths
            .into_iter()
            .map(|path| {
                let accepted = allowed
                    && (approved_paths.is_empty()
                        || approved_paths.iter().any(|item| item == &path));
                ReviewDecisionFileSummary {
                    path,
                    state: if accepted {
                        ReviewDecisionState::Accepted
                    } else {
                        ReviewDecisionState::Rejected
                    },
                    total_hunks: 0,
                    accepted_hunks: Vec::new(),
                    rejected_hunks: Vec::new(),
                }
            })
            .collect::<Vec<_>>();
        ReviewDecisionSummary {
            total_files: files.len(),
            accepted_files: files
                .iter()
                .filter(|file| file.state == ReviewDecisionState::Accepted)
                .count(),
            total_hunks: 0,
            accepted_hunks: 0,
            files,
        }
    }
}

// ── Diff parsing helpers ────────────────────────────────────────────

fn normalize_review_chunk_path(raw_path: &str, fallback_paths: &[String]) -> String {
    let trimmed = raw_path
        .trim()
        .trim_start_matches("a/")
        .trim_start_matches("b/");
    if trimmed.is_empty() || trimmed == "/dev/null" {
        return fallback_paths.first().cloned().unwrap_or_default();
    }
    if trimmed.starts_with('/') {
        return trimmed.to_string();
    }
    let mut matches = fallback_paths
        .iter()
        .filter(|path| path.ends_with(trimmed))
        .cloned()
        .collect::<Vec<_>>();
    if matches.len() == 1 {
        return matches.remove(0);
    }
    let file_name = trimmed.rsplit('/').next().unwrap_or(trimmed);
    matches = fallback_paths
        .iter()
        .filter(|path| path.rsplit('/').next().unwrap_or("") == file_name)
        .cloned()
        .collect::<Vec<_>>();
    if matches.len() == 1 {
        return matches.remove(0);
    }
    trimmed.to_string()
}

fn format_hunk_labels(hunks: &[usize]) -> String {
    if hunks.is_empty() {
        return "none".to_string();
    }
    hunks
        .iter()
        .map(|index| format!("h{}", index + 1))
        .collect::<Vec<_>>()
        .join(", ")
}

pub fn parse_mutation_review_chunks(
    diff: &str,
    fallback_paths: &[String],
) -> Vec<MutationReviewChunk> {
    let mut chunks: Vec<MutationReviewChunk> = Vec::new();
    let mut current_path = fallback_paths.first().cloned().unwrap_or_default();
    let mut current_lines: Vec<String> = Vec::new();
    let mut current_header = String::new();
    let mut hunk_indexes: HashMap<String, usize> = HashMap::new();
    for line in diff.lines() {
        if line.starts_with("diff --git ") || line.starts_with("--- ") {
            if !current_lines.is_empty() {
                let chunk_path = if current_path.is_empty() {
                    fallback_paths.first().cloned().unwrap_or_default()
                } else {
                    current_path.clone()
                };
                let next_index = hunk_indexes.entry(chunk_path.clone()).or_insert(0usize);
                chunks.push(MutationReviewChunk {
                    path: chunk_path,
                    hunk_index: *next_index,
                    header: current_header.clone(),
                    diff: current_lines.join("\n"),
                    selected: false,
                });
                *next_index += 1;
                current_lines.clear();
            }
            if line.starts_with("--- ") {
                continue;
            }
        }
        if let Some(raw_path) = line.strip_prefix("+++ ") {
            current_path = normalize_review_chunk_path(raw_path, fallback_paths);
            continue;
        }
        if line.starts_with("@@") {
            if !current_lines.is_empty() {
                let chunk_path = if current_path.is_empty() {
                    fallback_paths.first().cloned().unwrap_or_default()
                } else {
                    current_path.clone()
                };
                let next_index = hunk_indexes.entry(chunk_path.clone()).or_insert(0usize);
                chunks.push(MutationReviewChunk {
                    path: chunk_path,
                    hunk_index: *next_index,
                    header: current_header.clone(),
                    diff: current_lines.join("\n"),
                    selected: false,
                });
                *next_index += 1;
                current_lines.clear();
            }
            current_header = line.to_string();
            current_lines.push(line.to_string());
            continue;
        }
        if !current_lines.is_empty() {
            current_lines.push(line.to_string());
        }
    }
    if !current_lines.is_empty() {
        let chunk_path = if current_path.is_empty() {
            fallback_paths.first().cloned().unwrap_or_default()
        } else {
            current_path
        };
        let next_index = hunk_indexes.entry(chunk_path.clone()).or_insert(0usize);
        chunks.push(MutationReviewChunk {
            path: chunk_path,
            hunk_index: *next_index,
            header: current_header,
            diff: current_lines.join("\n"),
            selected: false,
        });
    }
    if chunks.is_empty() && !diff.trim().is_empty() {
        chunks.push(MutationReviewChunk {
            path: fallback_paths.first().cloned().unwrap_or_default(),
            hunk_index: 0,
            header: "Full diff".to_string(),
            diff: diff.to_string(),
            selected: false,
        });
    }
    chunks
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_mutation_review_chunks_extracts_per_file_hunks() {
        let diff = "\
diff --git a/src/demo.rs b/src/demo.rs
--- a/src/demo.rs
+++ b/src/demo.rs
@@ -1 +1 @@
-old
+new
diff --git a/src/other.rs b/src/other.rs
--- a/src/other.rs
+++ b/src/other.rs
@@ -3 +3 @@
-left
+right
";
        let chunks = parse_mutation_review_chunks(
            diff,
            &[
                "/tmp/src/demo.rs".to_string(),
                "/tmp/src/other.rs".to_string(),
            ],
        );
        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[0].path, "/tmp/src/demo.rs");
        assert_eq!(chunks[0].hunk_index, 0);
        assert_eq!(chunks[1].path, "/tmp/src/other.rs");
        assert_eq!(chunks[1].hunk_index, 0);
    }

    #[test]
    fn mutation_review_file_groups_preserve_file_order_and_counts() {
        let review = MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec![
                "/tmp/src/demo.rs".to_string(),
                "/tmp/src/other.rs".to_string(),
            ],
            diff: String::new(),
            checkpoint_id: None,
            changed: Some(true),
            message: String::new(),
            selected_path_index: 0,
            chunks: vec![
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: true,
                },
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 1,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
                MutationReviewChunk {
                    path: "/tmp/src/other.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -8 +8 @@".to_string(),
                    diff: "@@ -8 +8 @@\n-before\n+after".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 0,
        };
        let groups = review.file_groups();
        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0].path, "/tmp/src/demo.rs");
        assert_eq!(groups[0].chunk_indexes, vec![0, 1]);
        assert_eq!(groups[0].selected_chunks, 1);
        assert_eq!(groups[1].path, "/tmp/src/other.rs");
        assert_eq!(groups[1].chunk_indexes, vec![2]);
        assert_eq!(groups[1].selected_chunks, 0);
    }

    #[test]
    fn mutation_review_partial_chunk_summary_tracks_accept_and_reject_lines() {
        let review = MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec![
                "/tmp/src/demo.rs".to_string(),
                "/tmp/src/other.rs".to_string(),
            ],
            diff: String::new(),
            checkpoint_id: None,
            changed: Some(true),
            message: String::new(),
            selected_path_index: 0,
            chunks: vec![
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: false,
                },
                MutationReviewChunk {
                    path: "/tmp/src/demo.rs".to_string(),
                    hunk_index: 1,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
                MutationReviewChunk {
                    path: "/tmp/src/other.rs".to_string(),
                    hunk_index: 0,
                    header: "@@ -8 +8 @@".to_string(),
                    diff: "@@ -8 +8 @@\n-before\n+after".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 0,
        };
        let summary = review.build_decision_summary(
            true,
            &[],
            &[ApprovedReviewChunk {
                path: "/tmp/src/demo.rs".to_string(),
                hunk_index: 1,
            }],
        );
        assert_eq!(summary.headline(), "Accepted 1/3 hunks across 1/2 files");
        assert_eq!(summary.files.len(), 2);
        assert_eq!(summary.files[0].state, ReviewDecisionState::Partial);
        assert_eq!(
            summary.files[0].summary_line(),
            "/tmp/src/demo.rs: accepted h2; rejected h1"
        );
        assert_eq!(summary.files[1].state, ReviewDecisionState::Rejected);
        assert_eq!(
            summary.files[1].summary_line(),
            "/tmp/src/other.rs: rejected hunks h1"
        );
    }
}
