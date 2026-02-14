use std::collections::{HashSet, HashMap};

/// Import validation (Task 32)
pub struct ValidationResult {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

pub fn validate_seuss_source(source: &str) -> ValidationResult {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    let mut entity_names = HashSet::new();
    let mut rel_refs = Vec::new();

    for (line_num, line) in source.lines().enumerate() {
        let trimmed = line.trim();
        let line_no = line_num + 1;

        // Check for duplicate entity names
        if trimmed.starts_with("entity ") {
            let parts: Vec<&str> = trimmed.split_whitespace().collect();
            if parts.len() >= 2 {
                let name = parts[1];
                if !entity_names.insert(name.to_string()) {
                    errors.push(format!("line {}: duplicate entity name '{}'", line_no, name));
                }
            }
        }

        // Collect relationship references
        if trimmed.starts_with("rel ") {
            let parts: Vec<&str> = trimmed.split_whitespace().collect();
            if parts.len() >= 2 {
                rel_refs.push((line_no, parts[1].to_string()));
            }
            // Find target after arrow
            if let Some(arrow_end) = trimmed.find("-> ").or(trimmed.find("- ")) {
                let after = &trimmed[arrow_end + 2..].trim();
                let target = after.split_whitespace().next().unwrap_or("").trim_end_matches(';');
                rel_refs.push((line_no, target.to_string()));
            }
        }

        // Check date format
        let date_pattern = regex_lite_date_check(trimmed);
        for (pos, bad_date) in date_pattern {
            warnings.push(format!("line {}: possibly malformed date '{}'", line_no, bad_date));
        }
    }

    // Check for dangling references
    for (line_no, ref_name) in &rel_refs {
        if !ref_name.is_empty() && !entity_names.contains(ref_name) {
            errors.push(format!("line {}: dangling entity reference '{}'", line_no, ref_name));
        }
    }

    ValidationResult { errors, warnings }
}

fn regex_lite_date_check(line: &str) -> Vec<(usize, String)> {
    let mut results = Vec::new();
    // Simple heuristic: look for YYYY-MM-DD patterns with invalid months/days
    let chars: Vec<char> = line.chars().collect();
    let mut i = 0;
    while i + 9 < chars.len() {
        if chars[i].is_ascii_digit() && chars[i + 4] == '-' && chars[i + 7] == '-' {
            let date_str: String = chars[i..i + 10].iter().collect();
            let parts: Vec<&str> = date_str.split('-').collect();
            if parts.len() == 3 {
                if let (Ok(m), Ok(d)) = (parts[1].parse::<u32>(), parts[2].parse::<u32>()) {
                    if m > 12 || m == 0 || d > 31 || d == 0 {
                        results.push((i, date_str));
                    }
                }
            }
        }
        i += 1;
    }
    results
}
