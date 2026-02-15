use crate::model::types::*;
use crate::model::world::World;
/// Built-in functions
pub fn register_builtins(world: &World, args: &[Value], name: &str) -> Option<Value> {
    match name {
        "before" => {
            if args.len() == 2 {
                let t1 = value_to_ordinal(&args[0]);
                let t2 = value_to_ordinal(&args[1]);
                Some(Value::Bool(t1 < t2))
            } else {
                None
            }
        }
        "after" => {
            if args.len() == 2 {
                let t1 = value_to_ordinal(&args[0]);
                let t2 = value_to_ordinal(&args[1]);
                Some(Value::Bool(t1 > t2))
            } else {
                None
            }
        }
        "overlaps" => {
            if args.len() >= 2 {
                let r1 = value_to_time_range(world, &args[0]);
                let r2 = value_to_time_range(world, &args[1]);
                match (r1, r2) {
                    (Some(a), Some(b)) => Some(Value::Bool(a.overlaps(&b))),
                    _ => Some(Value::Bool(false)),
                }
            } else {
                Some(Value::Bool(false))
            }
        }
        "concurrent" => {
            if args.len() >= 2 {
                let e1_ranges = entity_ranges(world, &args[0]);
                let e2_ranges = entity_ranges(world, &args[1]);
                let overlap = e1_ranges.iter().any(|(tid1, tr1)| {
                    e2_ranges
                        .iter()
                        .any(|(tid2, tr2)| tid1 == tid2 && tr1.overlaps(tr2))
                });
                Some(Value::Bool(overlap))
            } else {
                Some(Value::Bool(false))
            }
        }
        "duration" => {
            if args.len() == 2 {
                let s = value_to_ordinal(&args[0]);
                let e = value_to_ordinal(&args[1]);
                Some(Value::Int(e - s))
            } else {
                None
            }
        }
        "entities_at" => {
            if args.len() >= 2 {
                let tl_name = match &args[0] {
                    Value::String(s) => s.clone(),
                    Value::Timeline(id) => world
                        .timelines
                        .get(id)
                        .map(|t| t.name.clone())
                        .unwrap_or_default(),
                    _ => return Some(Value::List(Vec::new())),
                };
                let tp_ord = value_to_ordinal(&args[1]);
                let tp = TimePoint::Abstract(tp_ord);
                if let Some(tl) = world.timeline_by_name(&tl_name) {
                    let full_range = TimeRange {
                        start: TimePoint::Abstract(i64::MIN),
                        end: TimePoint::Abstract(i64::MAX),
                        inclusive_end: true,
                    };
                    let entities: Vec<Value> = world
                        .entities_on_timeline(tl.id, &full_range)
                        .into_iter()
                        .filter(|e| {
                            e.timeline_appearances
                                .iter()
                                .any(|(tid, tr)| *tid == tl.id && tr.contains(&tp))
                        })
                        .map(|e| Value::String(e.name.clone()))
                        .collect();
                    Some(Value::List(entities))
                } else {
                    Some(Value::List(Vec::new()))
                }
            } else {
                Some(Value::List(Vec::new()))
            }
        }
        "relationships_of" => {
            if let Some(eid) = entity_id_from_value(world, args.first()) {
                let rels: Vec<Value> = world
                    .relationships
                    .iter()
                    .filter(|r| r.source_entity_id == eid || r.target_entity_id == eid)
                    .map(|r| {
                        let src = world
                            .entity_by_id(r.source_entity_id)
                            .map(|e| e.name.as_str())
                            .unwrap_or("?");
                        let tgt = world
                            .entity_by_id(r.target_entity_id)
                            .map(|e| e.name.as_str())
                            .unwrap_or("?");
                        Value::List(vec![
                            Value::String(src.to_string()),
                            Value::String(r.label.clone()),
                            Value::String(tgt.to_string()),
                            Value::Bool(r.directed),
                        ])
                    })
                    .collect();
                Some(Value::List(rels))
            } else {
                None
            }
        }
        "type_of" => {
            if let Some(eid) = entity_id_from_value(world, args.first()) {
                world
                    .entity_by_id(eid)
                    .map(|e| Value::String(e.type_id.clone()))
            } else {
                None
            }
        }
        "len" => {
            if let Some(Value::List(items)) = args.first() {
                Some(Value::Int(items.len() as i64))
            } else if let Some(Value::String(s)) = args.first() {
                Some(Value::Int(s.len() as i64))
            } else {
                None
            }
        }
        "print" => {
            for arg in args {
                print!("{}", arg);
            }
            println!();
            Some(Value::Null)
        }
        _ => None,
    }
}
fn value_to_ordinal(v: &Value) -> i64 {
    match v {
        Value::Int(n) => *n,
        Value::Date(tp) => tp.to_ordinal(),
        _ => 0,
    }
}
fn entity_id_from_value(world: &World, v: Option<&Value>) -> Option<Id> {
    match v? {
        Value::Entity(id) => Some(*id),
        Value::String(name) => world.entity_by_name(name).map(|e| e.id),
        _ => None,
    }
}
fn entity_ranges(world: &World, v: &Value) -> Vec<(Id, TimeRange)> {
    let eid = match v {
        Value::Entity(id) => Some(*id),
        Value::String(name) => world.entity_by_name(name).map(|e| e.id),
        _ => None,
    };
    eid.and_then(|id| world.entity_by_id(id))
        .map(|e| e.timeline_appearances.clone())
        .unwrap_or_default()
}
fn value_to_time_range(world: &World, v: &Value) -> Option<TimeRange> {
    match v {
        Value::Entity(id) => world
            .entity_by_id(*id)
            .and_then(|e| e.timeline_appearances.first())
            .map(|(_, tr)| tr.clone()),
        Value::List(items) if items.len() == 2 => {
            let s = value_to_ordinal(&items[0]);
            let e = value_to_ordinal(&items[1]);
            Some(TimeRange {
                start: TimePoint::Abstract(s),
                end: TimePoint::Abstract(e),
                inclusive_end: true,
            })
        }
        _ => None,
    }
}
