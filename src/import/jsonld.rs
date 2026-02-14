use serde_json::Value;

/// JSON-LD importer (Task 30)
/// Recognizes schema.org Person and Event types
pub fn import_jsonld(content: &str) -> Result<String, String> {
    let json: Value = serde_json::from_str(content)
        .map_err(|e| format!("invalid JSON: {}", e))?;

    let mut output = String::new();
    let mut min_year = 9999i32;
    let mut max_year = 0i32;
    let mut entities = Vec::new();

    let items = if let Some(graph) = json.get("@graph") {
        graph.as_array().cloned().unwrap_or_default()
    } else if json.is_array() {
        json.as_array().cloned().unwrap_or_default()
    } else {
        vec![json.clone()]
    };

    for item in &items {
        let type_val = item.get("@type").or_else(|| item.get("type"));
        let type_str = type_val.and_then(|v| v.as_str()).unwrap_or("");

        match type_str {
            "Person" | "schema:Person" | "http://schema.org/Person" => {
                let name = get_str(item, "name").unwrap_or("Unknown");
                let birth = get_str(item, "birthDate");
                let death = get_str(item, "deathDate");

                if let Some(b) = birth {
                    if let Some(y) = b.split('-').next().and_then(|s| s.parse::<i32>().ok()) {
                        min_year = min_year.min(y);
                        max_year = max_year.max(y);
                    }
                }
                if let Some(d) = death {
                    if let Some(y) = d.split('-').next().and_then(|s| s.parse::<i32>().ok()) {
                        max_year = max_year.max(y);
                    }
                }

                entities.push(("character", name.to_string(), birth.map(String::from), death.map(String::from)));
            }
            "Event" | "schema:Event" | "http://schema.org/Event" => {
                let name = get_str(item, "name").unwrap_or("Unknown");
                let start = get_str(item, "startDate");
                let end = get_str(item, "endDate").or(start);

                if let Some(s) = start {
                    if let Some(y) = s.split('-').next().and_then(|s| s.parse::<i32>().ok()) {
                        min_year = min_year.min(y);
                        max_year = max_year.max(y);
                    }
                }

                entities.push(("event", name.to_string(), start.map(String::from), end.map(String::from)));
            }
            _ => {}
        }
    }

    if min_year > max_year {
        min_year = 1900;
        max_year = 2000;
    }

    output.push_str(&format!("timeline main {{\n    kind: linear,\n    start: {}-01-01,\n    end: {}-12-31,\n}}\n\n",
        min_year, max_year));

    for (etype, name, start, end) in &entities {
        let safe_name = name.replace(' ', "_").replace('-', "_").replace('\'', "");
        let s = start.as_deref().unwrap_or(&format!("{}-01-01", min_year));
        let e = end.as_deref().unwrap_or(&format!("{}-12-31", max_year));
        output.push_str(&format!("entity {} : {} {{\n", safe_name, etype));
        output.push_str(&format!("    full_name: \"{}\",\n", name));
        output.push_str(&format!("    appears_on: main @ {}..{},\n", s, e));
        output.push_str("}\n\n");
    }

    Ok(output)
}

fn get_str<'a>(val: &'a Value, key: &str) -> Option<&'a str> {
    val.get(key).and_then(|v| v.as_str())
}
