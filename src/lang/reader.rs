use std::path::Path;

/// Read .seuss file handling UTF-8 BOM and normalizing line endings (Task 16)
pub fn read_seuss_file(path: &Path) -> Result<String, String> {
    if path.extension().and_then(|e| e.to_str()) != Some("seuss") {
        return Err(format!("expected .seuss file, got: {}", path.display()));
    }
    let bytes = std::fs::read(path)
        .map_err(|e| format!("failed to read {}: {}", path.display(), e))?;

    // Strip UTF-8 BOM
    let content = if bytes.starts_with(&[0xEF, 0xBB, 0xBF]) {
        String::from_utf8(bytes[3..].to_vec())
    } else {
        String::from_utf8(bytes)
    }
    .map_err(|e| format!("invalid UTF-8 in {}: {}", path.display(), e))?;

    // Normalize line endings
    Ok(content.replace("\r\n", "\n").replace("\r", "\n"))
}
