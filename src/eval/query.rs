use crate::model::world::World;
use crate::model::types::*;

/// Query DSL subset (Task 60)
/// Supports: select entities where type == "X" and appears_on("Y") and alive_at(N)
pub fn query_entities(world: &World, query: &str) -> Result<Vec<Id>, String> {
    let query = query.trim();

    if !query.starts_with("select entities") {
        return Err("query must start with 'select entities'".into());
    }

    let where_clause = query.strip_prefix("select entities")
        .unwrap_or("")
        .trim();

    let conditions = if where_clause.starts_with("where ") {
        parse_conditions(&where_clause[6..])
    } else {
        Vec::new()
    };

    let mut results = Vec::new();
    for entity in world.entities.values() {
        if matches_all(entity, &conditions, world) {
            results.push(entity.id);
        }
    }

    Ok(results)
}

#[derive(Debug)]
enum Condition {
    TypeEquals(String),
    AppearsOn(String),
    AliveAt(i64),
    NameContains(String),
    HasAttribute(String),
}

fn parse_conditions(s: &str) -> Vec<Condition> {
    let mut conditions = Vec::new();
    let parts: Vec<&str> = s.split(" and ").collect();

    for part in parts {
        let part = part.trim();
        if part.starts_with("type == ") || part.starts_with("type==\"") {
            let val = part.split("==").nth(1).unwrap_or("").trim().trim_matches('"');
            conditions.push(Condition::TypeEquals(val.to_string()));
        } else if part.starts_with("appears_on(") {
            let val = part.trim_start_matches("appears_on(\"").trim_end_matches("\")").trim_end_matches("\")")  ;
            conditions.push(Condition::AppearsOn(val.to_string()));
        } else if part.starts_with("alive_at(") {
            let val = part.trim_start_matches("alive_at(").trim_end_matches(')');
            if let Ok(n) = val.parse::<i64>() {
                conditions.push(Condition::AliveAt(n));
            }
        } else if part.starts_with("name contains ") {
            let val = part.strip_prefix("name contains ").unwrap_or("").trim_matches('"');
            conditions.push(Condition::NameContains(val.to_string()));
        } else if part.starts_with("has ") {
            let val = part.strip_prefix("has ").unwrap_or("");
            conditions.push(Condition::HasAttribute(val.to_string()));
        }
    }

    conditions
}

fn matches_all(entity: &Entity, conditions: &[Condition], world: &World) -> bool {
    for cond in conditions {
        match cond {
            Condition::TypeEquals(t) => {
                if entity.type_id != *t { return false; }
            }
            Condition::AppearsOn(tl_name) => {
                let appears = entity.timeline_appearances.iter().any(|(tid, _)| {
                    world.timelines.get(tid).map(|t| t.name == *tl_name).unwrap_or(false)
                });
                if !appears { return false; }
            }
            Condition::AliveAt(time) => {
                let alive = entity.timeline_appearances.iter().any(|(_, tr)| {
                    let s = tr.start.to_ordinal();
                    let e = tr.end.to_ordinal();
                    *time >= s && *time <= e
                });
                if !alive { return false; }
            }
            Condition::NameContains(s) => {
                if !entity.name.to_lowercase().contains(&s.to_lowercase()) { return false; }
            }
            Condition::HasAttribute(attr) => {
                if !entity.attributes.contains_key(attr) { return false; }
            }
        }
    }
    true
}
