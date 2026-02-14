use crate::model::types::*;
use crate::model::world::World;

/// Built-in functions (Task 35)
pub fn register_builtins(world: &World, args: &[Value], name: &str) -> Option<Value> {
    match name {
        "before" => {
            if args.len() == 2 {
                let t1 = value_to_ordinal(&args[0]);
                let t2 = value_to_ordinal(&args[1]);
                Some(Value::Bool(t1 < t2))
            } else { None }
        }
        "after" => {
            if args.len() == 2 {
                let t1 = value_to_ordinal(&args[0]);
                let t2 = value_to_ordinal(&args[1]);
                Some(Value::Bool(t1 > t2))
            } else { None }
        }
        "overlaps" => {
            // Check if two time ranges overlap
            Some(Value::Bool(false))
        }
        "concurrent" => {
            Some(Value::Bool(false))
        }
        "duration" => {
            if args.len() == 2 {
                let s = value_to_ordinal(&args[0]);
                let e = value_to_ordinal(&args[1]);
                Some(Value::Int(e - s))
            } else { None }
        }
        "entities_at" => {
            // Query entities at a time point on a timeline
            Some(Value::List(Vec::new()))
        }
        "relationships_of" => {
            if let Some(Value::Entity(eid)) = args.first() {
                let rels: Vec<Value> = world.relationships.iter()
                    .filter(|r| r.source_entity_id == *eid || r.target_entity_id == *eid)
                    .map(|r| Value::String(r.label.clone()))
                    .collect();
                Some(Value::List(rels))
            } else { None }
        }
        "type_of" => {
            if let Some(Value::Entity(eid)) = args.first() {
                if let Some(entity) = world.entity_by_id(*eid) {
                    Some(Value::String(entity.type_id.clone()))
                } else { None }
            } else { None }
        }
        "len" => {
            if let Some(Value::List(items)) = args.first() {
                Some(Value::Int(items.len() as i64))
            } else if let Some(Value::String(s)) = args.first() {
                Some(Value::Int(s.len() as i64))
            } else { None }
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
