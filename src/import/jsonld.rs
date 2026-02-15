use serde_json::Value;
use std::collections::HashMap;

/// JSON-LD importer (Task 30)
/// Recognizes schema.org Person and Event types, relationships, and @context
pub fn import_jsonld(content: &str) -> Result<String, String> {
    let json: Value = serde_json::from_str(content).map_err(|e| format!("invalid JSON: {}", e))?;

    // Resolve @context for compact IRI expansion
    let context = extract_context(&json);

    let mut output = String::new();
    let mut min_year = 9999i32;
    let mut max_year = 0i32;
    let mut entities = Vec::new();
    let mut relationships = Vec::new();

    let items = if let Some(graph) = json.get("@graph") {
        graph.as_array().cloned().unwrap_or_default()
    } else if json.is_array() {
        json.as_array().cloned().unwrap_or_default()
    } else {
        vec![json.clone()]
    };

    // Build name lookup from @id
    let mut id_to_name: HashMap<String, String> = HashMap::new();
    for item in &items {
        if let (Some(id), Some(name)) = (get_str(item, "@id"), get_str(item, "name")) {
            id_to_name.insert(id.to_string(), name.to_string());
        }
    }

    for item in &items {
        let type_val = item.get("@type").or_else(|| item.get("type"));
        let type_str = type_val
            .and_then(|v| v.as_str())
            .map(|s| expand_iri(s, &context))
            .unwrap_or_default();

        let name = get_str(item, "name").unwrap_or("Unknown");

        match type_str.as_str() {
            s if s.contains("Person") => {
                let birth = get_str(item, "birthDate");
                let death = get_str(item, "deathDate");

                update_year_range(birth, &mut min_year, &mut max_year);
                update_year_range(death, &mut min_year, &mut max_year);

                entities.push((
                    "character",
                    name.to_string(),
                    birth.map(String::from),
                    death.map(String::from),
                ));

                // Extract relationship properties
                extract_relationships(item, name, &context, &id_to_name, &mut relationships);
            }
            s if s.contains("Event") => {
                let start = get_str(item, "startDate");
                let end = get_str(item, "endDate").or(start);

                update_year_range(start, &mut min_year, &mut max_year);

                entities.push((
                    "event",
                    name.to_string(),
                    start.map(String::from),
                    end.map(String::from),
                ));
            }
            _ => {}
        }
    }

    if min_year > max_year {
        min_year = 1900;
        max_year = 2000;
    }

    output.push_str(&format!(
        "timeline main {{\n    kind: linear,\n    start: {}-01-01,\n    end: {}-12-31,\n}}\n\n",
        min_year, max_year
    ));

    for (etype, name, start, end) in &entities {
        let safe_name = sanitize_name(name);
        let default_start = format!("{}-01-01", min_year);
        let default_end = format!("{}-12-31", max_year);
        let s = start.as_deref().unwrap_or(&default_start);
        let e = end.as_deref().unwrap_or(&default_end);
        output.push_str(&format!("entity {} : {} {{\n", safe_name, etype));
        output.push_str(&format!("    full_name: \"{}\",\n", name));
        output.push_str(&format!("    appears_on: main @ {}..{},\n", s, e));
        output.push_str("}\n\n");
    }

    for (source, label, target) in &relationships {
        let src = sanitize_name(source);
        let tgt = sanitize_name(target);
        output.push_str(&format!("rel {} -[\"{}\"]-> {};\n", src, label, tgt));
    }

    Ok(output)
}

/// Extract @context mappings for compact IRI expansion
fn extract_context(json: &Value) -> HashMap<String, String> {
    let mut ctx = HashMap::new();
    if let Some(context) = json.get("@context") {
        if let Some(obj) = context.as_object() {
            for (key, val) in obj {
                if let Some(s) = val.as_str() {
                    ctx.insert(key.clone(), s.to_string());
                }
            }
        }
    }
    ctx
}

/// Expand a compact IRI using @context (e.g., "schema:Person" -> "http://schema.org/Person")
fn expand_iri(iri: &str, context: &HashMap<String, String>) -> String {
    if iri.contains("://") {
        return iri.to_string();
    }
    if let Some(colon_pos) = iri.find(':') {
        let prefix = &iri[..colon_pos];
        let suffix = &iri[colon_pos + 1..];
        if let Some(base) = context.get(prefix) {
            return format!("{}{}", base, suffix);
        }
    }
    iri.to_string()
}

/// Known schema.org relationship properties and their labels
const REL_PROPERTIES: &[(&str, &str)] = &[
    ("knows", "knows"),
    ("parent", "parent"),
    ("children", "parent"), // reverse: target is parent of source
    ("spouse", "spouse"),
    ("sibling", "sibling"),
    ("colleague", "colleague"),
    ("follows", "follows"),
    ("memberOf", "member_of"),
    ("worksFor", "works_for"),
];

/// Extract relationship properties from a JSON-LD item
fn extract_relationships(
    item: &Value,
    source_name: &str,
    context: &HashMap<String, String>,
    id_to_name: &HashMap<String, String>,
    relationships: &mut Vec<(String, String, String)>,
) {
    for (prop, label) in REL_PROPERTIES {
        let expanded = expand_iri(&format!("schema:{}", prop), context);
        // Check both compact and expanded forms
        let val = item.get(*prop).or_else(|| item.get(&expanded));
        if let Some(v) = val {
            let targets = if v.is_array() {
                v.as_array().cloned().unwrap_or_default()
            } else {
                vec![v.clone()]
            };
            for target in targets {
                let target_name = if let Some(name) = target.as_str() {
                    id_to_name
                        .get(name)
                        .cloned()
                        .unwrap_or_else(|| name.to_string())
                } else if let Some(name) = target.get("name").and_then(|n| n.as_str()) {
                    name.to_string()
                } else if let Some(id) = target.get("@id").and_then(|n| n.as_str()) {
                    id_to_name
                        .get(id)
                        .cloned()
                        .unwrap_or_else(|| id.to_string())
                } else {
                    continue;
                };
                relationships.push((source_name.to_string(), label.to_string(), target_name));
            }
        }
    }
}

fn update_year_range(date: Option<&str>, min_year: &mut i32, max_year: &mut i32) {
    if let Some(d) = date {
        if let Some(y) = d.split('-').next().and_then(|s| s.parse::<i32>().ok()) {
            *min_year = (*min_year).min(y);
            *max_year = (*max_year).max(y);
        }
    }
}

fn sanitize_name(name: &str) -> String {
    name.replace(' ', "_").replace('-', "_").replace('\'', "")
}

fn get_str<'a>(val: &'a Value, key: &str) -> Option<&'a str> {
    val.get(key).and_then(|v| v.as_str())
}
