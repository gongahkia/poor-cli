use crate::model::types::*;
use crate::model::world::World;

/// Query DSL subset (Task 60)
/// Supports: select entities where type == "X" and appears_on("Y") and alive_at(N)
///           order by <field> asc|desc
///           overlaps <date>..<date>
pub fn query_entities(world: &World, query: &str) -> Result<Vec<Id>, String> {
    let query = query.trim();

    if !query.starts_with("select entities") {
        return Err("query must start with 'select entities'".into());
    }

    let rest = query.strip_prefix("select entities").unwrap_or("").trim();

    // Split off "order by" clause if present
    let (where_part, order_clause) = if let Some(pos) = rest.to_lowercase().find("order by") {
        (&rest[..pos], Some(rest[pos + 8..].trim()))
    } else {
        (rest, None)
    };

    let conditions = if where_part.trim().starts_with("where ") {
        parse_conditions(&where_part.trim()[6..])
    } else {
        Vec::new()
    };

    let mut results: Vec<&Entity> = world
        .entities
        .values()
        .filter(|e| matches_all(e, &conditions, world))
        .collect();

    // Apply ordering
    if let Some(order) = order_clause {
        apply_ordering(&mut results, order);
    }

    Ok(results.iter().map(|e| e.id).collect())
}

#[derive(Debug)]
enum Condition {
    TypeEquals(String),
    AppearsOn(String),
    AliveAt(i64),
    NameContains(String),
    HasAttribute(String),
    Overlaps(i64, i64),
}

fn parse_conditions(s: &str) -> Vec<Condition> {
    let mut conditions = Vec::new();
    // Normalize whitespace
    let s = s.split_whitespace().collect::<Vec<_>>().join(" ");
    let parts: Vec<&str> = s.split(" and ").collect();

    for part in parts {
        let part = part.trim();
        if part.starts_with("type == ")
            || part.starts_with("type==\"")
            || part.starts_with("type == '")
        {
            let val = extract_quoted_value(part.split("==").nth(1).unwrap_or("").trim());
            conditions.push(Condition::TypeEquals(val));
        } else if part.starts_with("appears_on(") {
            let val =
                extract_quoted_value(part.trim_start_matches("appears_on(").trim_end_matches(')'));
            conditions.push(Condition::AppearsOn(val));
        } else if part.starts_with("alive_at(") {
            let val = part.trim_start_matches("alive_at(").trim_end_matches(')');
            if let Ok(n) = val.parse::<i64>() {
                conditions.push(Condition::AliveAt(n));
            }
        } else if part.starts_with("name contains ") {
            let val = extract_quoted_value(part.strip_prefix("name contains ").unwrap_or(""));
            conditions.push(Condition::NameContains(val));
        } else if part.starts_with("has ") {
            let val = part.strip_prefix("has ").unwrap_or("").trim();
            conditions.push(Condition::HasAttribute(val.to_string()));
        } else if part.starts_with("overlaps ") {
            let range = part.strip_prefix("overlaps ").unwrap_or("").trim();
            if let Some((start, end)) = range.split_once("..") {
                if let (Ok(s), Ok(e)) = (start.trim().parse::<i64>(), end.trim().parse::<i64>()) {
                    conditions.push(Condition::Overlaps(s, e));
                }
            }
        }
    }

    conditions
}

/// Extract value from both single and double quoted strings, or unquoted
fn extract_quoted_value(s: &str) -> String {
    let s = s.trim();
    if (s.starts_with('"') && s.ends_with('"')) || (s.starts_with('\'') && s.ends_with('\'')) {
        s[1..s.len() - 1].to_string()
    } else {
        s.trim_matches('"').trim_matches('\'').to_string()
    }
}

/// Apply "order by <field> asc|desc" to results
fn apply_ordering(results: &mut Vec<&Entity>, order_clause: &str) {
    let parts: Vec<&str> = order_clause.split_whitespace().collect();
    let field = parts.first().map(|s| *s).unwrap_or("name");
    let descending = parts
        .get(1)
        .map(|s| s.to_lowercase() == "desc")
        .unwrap_or(false);

    results.sort_by(|a, b| {
        let cmp = match field {
            "name" => a.name.cmp(&b.name),
            "type" => a.type_id.cmp(&b.type_id),
            "start" => {
                let a_start = a
                    .timeline_appearances
                    .first()
                    .map(|(_, tr)| tr.start.to_ordinal())
                    .unwrap_or(0);
                let b_start = b
                    .timeline_appearances
                    .first()
                    .map(|(_, tr)| tr.start.to_ordinal())
                    .unwrap_or(0);
                a_start.cmp(&b_start)
            }
            "end" => {
                let a_end = a
                    .timeline_appearances
                    .first()
                    .map(|(_, tr)| tr.end.to_ordinal())
                    .unwrap_or(0);
                let b_end = b
                    .timeline_appearances
                    .first()
                    .map(|(_, tr)| tr.end.to_ordinal())
                    .unwrap_or(0);
                a_end.cmp(&b_end)
            }
            _ => a.name.cmp(&b.name),
        };
        if descending {
            cmp.reverse()
        } else {
            cmp
        }
    });
}

fn matches_all(entity: &Entity, conditions: &[Condition], world: &World) -> bool {
    for cond in conditions {
        match cond {
            Condition::TypeEquals(t) => {
                if entity.type_id != *t {
                    return false;
                }
            }
            Condition::AppearsOn(tl_name) => {
                let appears = entity.timeline_appearances.iter().any(|(tid, _)| {
                    world
                        .timelines
                        .get(tid)
                        .map(|t| t.name == *tl_name)
                        .unwrap_or(false)
                });
                if !appears {
                    return false;
                }
            }
            Condition::AliveAt(time) => {
                let alive = entity.timeline_appearances.iter().any(|(_, tr)| {
                    let s = tr.start.to_ordinal();
                    let e = tr.end.to_ordinal();
                    *time >= s && *time <= e
                });
                if !alive {
                    return false;
                }
            }
            Condition::NameContains(s) => {
                if !entity.name.to_lowercase().contains(&s.to_lowercase()) {
                    return false;
                }
            }
            Condition::HasAttribute(attr) => {
                if !entity.attributes.contains_key(attr) {
                    return false;
                }
            }
            Condition::Overlaps(range_start, range_end) => {
                let overlaps = entity.timeline_appearances.iter().any(|(_, tr)| {
                    let s = tr.start.to_ordinal();
                    let e = tr.end.to_ordinal();
                    s < *range_end && e > *range_start
                });
                if !overlaps {
                    return false;
                }
            }
        }
    }
    true
}
