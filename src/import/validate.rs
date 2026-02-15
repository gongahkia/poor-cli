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
    let mut timeline_names = HashSet::new();
    let mut type_refs = Vec::new();
    let mut timeline_refs = Vec::new();

    for (line_num, line) in source.lines().enumerate() {
        let trimmed = line.trim();
        let line_no = line_num + 1;

        // Collect timeline declarations
        if trimmed.starts_with("timeline ") {
            let parts: Vec<&str> = trimmed.split_whitespace().collect();
            if parts.len() >= 2 {
                timeline_names.insert(parts[1].trim_end_matches('{').to_string());
            }
        }

        // Check for duplicate entity names and collect type refs
        if trimmed.starts_with("entity ") {
            let parts: Vec<&str> = trimmed.split_whitespace().collect();
            if parts.len() >= 2 {
                let name = parts[1];
                if !entity_names.insert(name.to_string()) {
                    errors.push(format!("line {}: duplicate entity name '{}'", line_no, name));
                }
                // Check for type reference after ':'
                if let Some(colon_pos) = parts.iter().position(|p| *p == ":") {
                    if let Some(type_name) = parts.get(colon_pos + 1) {
                        let tn = type_name.trim_end_matches('{').to_string();
                        type_refs.push((line_no, tn));
                    }
                }
            }
        }

        // Collect appears_on timeline references
        if trimmed.contains("appears_on:") || trimmed.contains("appears_on :") {
            if let Some(tl_ref) = trimmed.split("appears_on").nth(1) {
                let tl_name = tl_ref.trim_start_matches(':').trim().split_whitespace().next()
                    .unwrap_or("").trim_end_matches(',');
                if !tl_name.is_empty() && !tl_name.starts_with('@') {
                    timeline_refs.push((line_no, tl_name.to_string()));
                }
            }
        }

        // Collect relationship references
        if trimmed.starts_with("rel ") {
            let parts: Vec<&str> = trimmed.split_whitespace().collect();
            if parts.len() >= 2 {
                rel_refs.push((line_no, parts[1].to_string()));
            }
            if let Some(arrow_end) = trimmed.find("-> ").or(trimmed.find("- ")) {
                let after = &trimmed[arrow_end + 2..].trim();
                let target = after.split_whitespace().next().unwrap_or("").trim_end_matches(';');
                rel_refs.push((line_no, target.to_string()));
            }
        }

        // Check date format using chrono
        let date_issues = validate_dates_in_line(trimmed);
        for bad_date in date_issues {
            warnings.push(format!("line {}: invalid date '{}' (expected YYYY-MM-DD)", line_no, bad_date));
        }
    }

    // Check for dangling entity references
    for (line_no, ref_name) in &rel_refs {
        if !ref_name.is_empty() && !entity_names.contains(ref_name) {
            errors.push(format!("line {}: dangling entity reference '{}'", line_no, ref_name));
        }
    }

    // Check for dangling timeline references
    for (line_no, tl_name) in &timeline_refs {
        if !timeline_names.contains(tl_name) {
            errors.push(format!("line {}: unknown timeline '{}'", line_no, tl_name));
        }
    }

    // Check type references against known builtins
    let builtins: HashSet<&str> = ["character", "event", "location", "artifact", "faction", "org", "entity"]
        .iter().copied().collect();
    for (line_no, type_name) in &type_refs {
        if !builtins.contains(type_name.as_str()) {
            warnings.push(format!("line {}: type '{}' is not a known builtin (may be user-defined)", line_no, type_name));
        }
    }

    ValidationResult { errors, warnings }
}

/// Validate date strings in a line using chrono::NaiveDate::parse_from_str
fn validate_dates_in_line(line: &str) -> Vec<String> {
    let mut bad_dates = Vec::new();
    let chars: Vec<char> = line.chars().collect();
    let mut i = 0;
    while i + 9 < chars.len() {
        if chars[i].is_ascii_digit() && chars[i + 4] == '-' && chars[i + 7] == '-'
            && chars[i + 5].is_ascii_digit() && chars[i + 8].is_ascii_digit()
        {
            let date_str: String = chars[i..i + 10].iter().collect();
            if chrono::NaiveDate::parse_from_str(&date_str, "%Y-%m-%d").is_err() {
                bad_dates.push(date_str);
            }
            i += 10;
        } else {
            i += 1;
        }
    }
    bad_dates
}
