/// GEDCOM 5.5.1 parser and mapper (Tasks 28-29)

#[derive(Debug, Clone)]
pub struct GedcomRecord {
    pub level: u32,
    pub tag: String,
    pub value: String,
    pub children: Vec<GedcomRecord>,
}

/// Tokenize GEDCOM into level-tag-value triples, handle CONC/CONT
pub fn parse_gedcom(content: &str) -> Vec<GedcomRecord> {
    let mut records: Vec<GedcomRecord> = Vec::new();
    let mut stack: Vec<GedcomRecord> = Vec::new();

    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() { continue; }

        let parts: Vec<&str> = line.splitn(3, ' ').collect();
        if parts.is_empty() { continue; }

        let level: u32 = match parts[0].parse() {
            Ok(l) => l,
            Err(_) => continue,
        };

        let (tag, value) = if parts.len() >= 3 {
            if parts[1].starts_with('@') {
                // Cross-reference: @I1@ INDI
                (parts[2].to_string(), parts[1].to_string())
            } else {
                (parts[1].to_string(), parts[2..].join(" "))
            }
        } else if parts.len() == 2 {
            (parts[1].to_string(), String::new())
        } else {
            continue;
        };

        let record = GedcomRecord { level, tag: tag.clone(), value, children: Vec::new() };

        // Handle CONC/CONT at any nesting depth
        if tag == "CONC" || tag == "CONT" {
            let target = find_concat_target(&mut stack, level);
            if let Some(parent) = target {
                if tag == "CONT" {
                    parent.value.push('\n');
                }
                parent.value.push_str(&record.value);
                continue;
            }
        }

        // Pop stack to find parent
        while let Some(top) = stack.last() {
            if top.level >= level {
                let completed = stack.pop().unwrap();
                if let Some(parent) = stack.last_mut() {
                    parent.children.push(completed);
                } else {
                    records.push(completed);
                }
            } else {
                break;
            }
        }

        stack.push(record);
    }

    // Drain stack
    while let Some(completed) = stack.pop() {
        if let Some(parent) = stack.last_mut() {
            parent.children.push(completed);
        } else {
            records.push(completed);
        }
    }

    records
}

/// Map GEDCOM to .seuss source (Task 29)
pub fn gedcom_to_seuss(records: &[GedcomRecord]) -> String {
    let mut output = String::new();
    let mut min_year = 9999i32;
    let mut max_year = 0i32;

    // First pass: collect individuals and dates
    let mut individuals: Vec<(String, String, Option<String>, Option<String>)> = Vec::new();
    let mut families: Vec<(String, Option<String>, Option<String>, Vec<String>)> = Vec::new();

    for record in records {
        match record.tag.as_str() {
            "INDI" => {
                let id = sanitize_id(&record.value);
                let name = find_child_value(&record.children, "NAME")
                    .unwrap_or_else(|| id.clone())
                    .replace('/', "")
                    .trim()
                    .to_string();
                let birth = find_event_date(&record.children, "BIRT");
                let death = find_event_date(&record.children, "DEAT");

                if let Some(ref b) = birth {
                    if let Some(y) = extract_year(b) {
                        min_year = min_year.min(y);
                        max_year = max_year.max(y);
                    }
                }
                if let Some(ref d) = death {
                    if let Some(y) = extract_year(d) {
                        max_year = max_year.max(y);
                    }
                }

                individuals.push((id, name, birth, death));
            }
            "FAM" => {
                let id = sanitize_id(&record.value);
                let husb = find_child_value(&record.children, "HUSB").map(|s| sanitize_id(&s));
                let wife = find_child_value(&record.children, "WIFE").map(|s| sanitize_id(&s));
                let children: Vec<String> = record.children.iter()
                    .filter(|c| c.tag == "CHIL")
                    .map(|c| sanitize_id(&c.value))
                    .collect();
                families.push((id, husb, wife, children));
            }
            _ => {}
        }
    }

    if min_year > max_year {
        min_year = 1800;
        max_year = 2000;
    }

    // Generate timeline
    output.push_str(&format!("timeline main {{\n    kind: linear,\n    start: {}-01-01,\n    end: {}-12-31,\n}}\n\n",
        min_year, max_year));

    // Generate entities
    for (id, name, birth, death) in &individuals {
        let safe_name = name.replace(' ', "_").replace('-', "_");
        let default_start = format!("{}-01-01", min_year);
        let default_end = format!("{}-12-31", max_year);
        let start = birth.as_deref().unwrap_or(&default_start);
        let end = death.as_deref().unwrap_or(&default_end);
        output.push_str(&format!("entity {} : character {{\n", safe_name));
        output.push_str(&format!("    full_name: \"{}\",\n", name));
        output.push_str(&format!("    appears_on: main @ {}..{},\n", start, end));
        output.push_str("}\n\n");
    }

    // Generate relationships
    for (_, husb, wife, children) in &families {
        if let (Some(h), Some(w)) = (husb, wife) {
            let h_name = find_name_by_id(&individuals, h);
            let w_name = find_name_by_id(&individuals, w);
            output.push_str(&format!("rel {} -[\"spouse\"]- {};\n", h_name, w_name));
        }
        for child in children {
            let c_name = find_name_by_id(&individuals, child);
            if let Some(h) = husb {
                let h_name = find_name_by_id(&individuals, h);
                output.push_str(&format!("rel {} -[\"parent\"]-> {};\n", h_name, c_name));
            }
            if let Some(w) = wife {
                let w_name = find_name_by_id(&individuals, w);
                output.push_str(&format!("rel {} -[\"parent\"]-> {};\n", w_name, c_name));
            }
        }
    }

    output
}

/// Find the record that CONC/CONT should append to based on nesting level.
fn find_concat_target(stack: &mut Vec<GedcomRecord>, level: u32) -> Option<&mut GedcomRecord> {
    if level == 0 || stack.is_empty() { return None; }
    // Find the nearest record in the stack whose level is level - 1
    let target_level = level - 1;
    let idx = stack.iter().rposition(|r| r.level == target_level);
    match idx {
        Some(i) => Some(&mut stack[i]),
        None => stack.last_mut(),
    }
}

/// Validation warning for GEDCOM structure issues
#[derive(Debug)]
pub struct GedcomWarning {
    pub record_id: String,
    pub message: String,
}

/// Validate GEDCOM structure: INDI must have NAME, FAM must have HUSB/WIFE/CHIL
pub fn validate_gedcom(records: &[GedcomRecord]) -> Vec<GedcomWarning> {
    let mut warnings = Vec::new();
    for record in records {
        match record.tag.as_str() {
            "INDI" => {
                let id = &record.value;
                if find_child_value(&record.children, "NAME").is_none() {
                    warnings.push(GedcomWarning {
                        record_id: id.clone(),
                        message: "INDI record missing NAME tag".into(),
                    });
                }
            }
            "FAM" => {
                let id = &record.value;
                let has_husb = record.children.iter().any(|c| c.tag == "HUSB");
                let has_wife = record.children.iter().any(|c| c.tag == "WIFE");
                let has_chil = record.children.iter().any(|c| c.tag == "CHIL");
                if !has_husb && !has_wife && !has_chil {
                    warnings.push(GedcomWarning {
                        record_id: id.clone(),
                        message: "FAM record missing HUSB, WIFE, and CHIL tags".into(),
                    });
                }
            }
            _ => {}
        }
    }
    warnings
}

fn sanitize_id(s: &str) -> String {
    s.replace('@', "").replace(' ', "_")
}

fn find_child_value(children: &[GedcomRecord], tag: &str) -> Option<String> {
    children.iter().find(|c| c.tag == tag).map(|c| c.value.clone())
}

fn find_event_date(children: &[GedcomRecord], event_tag: &str) -> Option<String> {
    children.iter()
        .find(|c| c.tag == event_tag)
        .and_then(|c| find_child_value(&c.children, "DATE"))
        .and_then(|d| normalize_date(&d))
}

fn normalize_date(s: &str) -> Option<String> {
    let parts: Vec<&str> = s.split_whitespace().collect();
    match parts.len() {
        1 => {
            if let Ok(y) = parts[0].parse::<i32>() {
                Some(format!("{:04}-01-01", y))
            } else { None }
        }
        2 => {
            let month = month_to_num(parts[0])?;
            let year: i32 = parts[1].parse().ok()?;
            Some(format!("{:04}-{:02}-01", year, month))
        }
        3 => {
            let day: u32 = parts[0].parse().ok()?;
            let month = month_to_num(parts[1])?;
            let year: i32 = parts[2].parse().ok()?;
            Some(format!("{:04}-{:02}-{:02}", year, month, day))
        }
        _ => None,
    }
}

fn month_to_num(m: &str) -> Option<u32> {
    match m.to_uppercase().as_str() {
        "JAN" => Some(1), "FEB" => Some(2), "MAR" => Some(3),
        "APR" => Some(4), "MAY" => Some(5), "JUN" => Some(6),
        "JUL" => Some(7), "AUG" => Some(8), "SEP" => Some(9),
        "OCT" => Some(10), "NOV" => Some(11), "DEC" => Some(12),
        _ => None,
    }
}

fn extract_year(date: &str) -> Option<i32> {
    date.split('-').next()?.parse().ok()
}

fn find_name_by_id(individuals: &[(String, String, Option<String>, Option<String>)], id: &str) -> String {
    individuals.iter()
        .find(|(i, _, _, _)| i == id)
        .map(|(_, name, _, _)| name.replace(' ', "_").replace('-', "_"))
        .unwrap_or_else(|| id.replace(' ', "_"))
}
