use std::collections::HashSet;
use std::path::{Path, PathBuf};

/// Module/import system (Task 35)
/// Resolves and tracks imported files to detect circular imports
#[derive(Debug, Default)]
pub struct ModuleSystem {
    loaded: HashSet<PathBuf>,
}

impl ModuleSystem {
    pub fn new() -> Self {
        Self {
            loaded: HashSet::new(),
        }
    }

    /// Resolve an import path relative to the current file
    pub fn resolve(&self, import_path: &str, current_file: &Path) -> Result<PathBuf, String> {
        let base = current_file.parent().unwrap_or(Path::new("."));
        let resolved = base.join(import_path);

        if !resolved.exists() {
            return Err(format!("import not found: {}", resolved.display()));
        }

        Ok(resolved
            .canonicalize()
            .map_err(|e| format!("path error: {}", e))?)
    }

    /// Check and mark a file as loaded; returns error if circular
    pub fn load(&mut self, path: &Path) -> Result<(), String> {
        let canonical = path
            .canonicalize()
            .map_err(|e| format!("path error: {}", e))?;

        if self.loaded.contains(&canonical) {
            return Err(format!("circular import detected: {}", canonical.display()));
        }

        self.loaded.insert(canonical);
        Ok(())
    }

    pub fn is_loaded(&self, path: &Path) -> bool {
        path.canonicalize()
            .map(|p| self.loaded.contains(&p))
            .unwrap_or(false)
    }
}
