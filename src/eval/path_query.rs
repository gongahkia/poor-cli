use std::collections::{HashMap, HashSet, VecDeque};
use crate::model::world::World;
use crate::model::types::Id;

/// Relationship path query (Task 46)
/// Returns shortest path between two entities via relationships
pub fn find_path(world: &World, source_id: Id, target_id: Id, max_hops: Option<usize>) -> Option<Vec<(Id, String, Id)>> {
    if source_id == target_id {
        return Some(Vec::new());
    }

    let max = max_hops.unwrap_or(usize::MAX);

    // BFS
    let mut visited: HashSet<Id> = HashSet::new();
    let mut queue: VecDeque<(Id, Vec<(Id, String, Id)>)> = VecDeque::new();

    visited.insert(source_id);
    queue.push_back((source_id, Vec::new()));

    while let Some((current, path)) = queue.pop_front() {
        if path.len() >= max {
            continue;
        }

        // Find all relationships involving current entity
        for rel in &world.relationships {
            let (neighbor, directed_from_current) = if rel.source_entity_id == current {
                (rel.target_entity_id, true)
            } else if rel.target_entity_id == current && !rel.directed {
                (rel.source_entity_id, false)
            } else {
                continue;
            };

            if visited.contains(&neighbor) {
                continue;
            }

            let mut new_path = path.clone();
            new_path.push((current, rel.label.clone(), neighbor));

            if neighbor == target_id {
                return Some(new_path);
            }

            visited.insert(neighbor);
            queue.push_back((neighbor, new_path));
        }
    }

    None
}

/// Format path as readable string
pub fn format_path(world: &World, path: &[(Id, String, Id)]) -> String {
    if path.is_empty() {
        return "(same entity)".to_string();
    }

    let mut parts = Vec::new();
    for (from, label, to) in path {
        let from_name = world.entities.get(from).map(|e| e.name.as_str()).unwrap_or("?");
        let to_name = world.entities.get(to).map(|e| e.name.as_str()).unwrap_or("?");
        parts.push(format!("{} -[{}]-> {}", from_name, label, to_name));
    }
    parts.join(" → ")
}
