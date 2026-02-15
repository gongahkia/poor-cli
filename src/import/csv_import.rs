use std::collections::{HashMap, HashSet};

/// Import error with line context
#[derive(Debug)]
pub struct ImportError {
    pub line: usize,
    pub message: String,
}

impl std::fmt::Display for ImportError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

/// Parse a CSV line respecting double-quoted fields containing commas and escaped quotes.
fn parse_csv_fields(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut chars = line.chars().peekable();

    while let Some(c) = chars.next() {
        if in_quotes {
            if c == '"' {
                if chars.peek() == Some(&'"') {
                    // Escaped quote ""
                    current.push('"');
                    chars.next();
                } else {
                    in_quotes = false;
                }
            } else {
                current.push(c);
            }
        } else {
            match c {
                '"' => in_quotes = true,
                ',' => {
                    fields.push(current.trim().to_string());
                    current = String::new();
                }
                _ => current.push(c),
            }
        }
    }
    fields.push(current.trim().to_string());
    fields
}

/// Parse CSV into .seuss entity declarations (Task 26)
/// Columns: name, type, timeline, start, end, [attr1, attr2, ...]
pub fn import_entities_csv(content: &str) -> Result<String, Vec<ImportError>> {
    let mut output = String::new();
    let mut errors = Vec::new();
    let lines: Vec<&str> = content.lines().collect();

    if lines.is_empty() {
        errors.push(ImportError { line: 0, message: "empty CSV".into() });
        return Err(errors);
    }

    let headers: Vec<String> = parse_csv_fields(lines[0]);
    let name_idx = headers.iter().position(|h| h == "name");
    let type_idx = headers.iter().position(|h| h == "type");
    let timeline_idx = headers.iter().position(|h| h == "timeline");
    let start_idx = headers.iter().position(|h| h == "start");
    let end_idx = headers.iter().position(|h| h == "end");

    if name_idx.is_none() {
        errors.push(ImportError { line: 1, message: "missing 'name' column".into() });
        return Err(errors);
    }

    let extra_attrs: Vec<(usize, String)> = headers.iter().enumerate()
        .filter(|(_, h)| !["name", "type", "timeline", "start", "end"].contains(&h.as_str()))
        .map(|(i, h)| (i, h.clone()))
        .collect();

    for (line_num, line) in lines[1..].iter().enumerate() {
        let cols: Vec<String> = parse_csv_fields(line);
        let line_no = line_num + 2;

        let name = match name_idx {
            Some(i) => cols.get(i).cloned().unwrap_or_default(),
            None => continue,
        };
        if name.is_empty() {
            errors.push(ImportError { line: line_no, message: "empty name".into() });
            continue;
        }

        let entity_type = type_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("entity");
        let timeline = timeline_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");
        let start = start_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");
        let end = end_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");

        output.push_str(&format!("entity {} : {} {{\n", name, entity_type));

        for (i, attr_name) in &extra_attrs {
            if let Some(val) = cols.get(*i) {
                if !val.is_empty() {
                    // Try to detect type
                    if val.parse::<i64>().is_ok() {
                        output.push_str(&format!("    {}: {},\n", attr_name, val));
                    } else {
                        output.push_str(&format!("    {}: \"{}\",\n", attr_name, val));
                    }
                }
            }
        }

        if !timeline.is_empty() && !start.is_empty() && !end.is_empty() {
            output.push_str(&format!("    appears_on: {} @ {}..{},\n", timeline, start, end));
        }

        output.push_str("}\n\n");
    }

    if errors.is_empty() { Ok(output) } else { Err(errors) }
}

/// Parse CSV into .seuss relationship declarations (Task 27)
/// Columns: source, target, label, start, end
pub fn import_relationships_csv(content: &str) -> Result<String, Vec<ImportError>> {
    let mut output = String::new();
    let mut errors = Vec::new();
    let lines: Vec<&str> = content.lines().collect();

    if lines.is_empty() {
        errors.push(ImportError { line: 0, message: "empty CSV".into() });
        return Err(errors);
    }

    let headers: Vec<String> = parse_csv_fields(lines[0]);
    let source_idx = headers.iter().position(|h| h == "source");
    let target_idx = headers.iter().position(|h| h == "target");
    let label_idx = headers.iter().position(|h| h == "label");
    let start_idx = headers.iter().position(|h| h == "start");
    let end_idx = headers.iter().position(|h| h == "end");

    if source_idx.is_none() || target_idx.is_none() {
        errors.push(ImportError { line: 1, message: "missing 'source' or 'target' column".into() });
        return Err(errors);
    }

    for (line_num, line) in lines[1..].iter().enumerate() {
        let cols: Vec<String> = parse_csv_fields(line);
        let line_no = line_num + 2;

        let source = source_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");
        let target = target_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");
        let label = label_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");

        if source.is_empty() || target.is_empty() {
            errors.push(ImportError { line: line_no, message: "empty source or target".into() });
            continue;
        }

        let start = start_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");
        let end = end_idx.and_then(|i| cols.get(i)).map(|s| s.as_str()).unwrap_or("");

        if !label.is_empty() {
            output.push_str(&format!("rel {} -[\"{}\"]-> {}", source, label, target));
        } else {
            output.push_str(&format!("rel {} --> {}", source, target));
        }

        if !start.is_empty() && !end.is_empty() {
            output.push_str(&format!(" @ {}..{}", start, end));
        }
        output.push_str(";\n");
    }

    if errors.is_empty() { Ok(output) } else { Err(errors) }
}
