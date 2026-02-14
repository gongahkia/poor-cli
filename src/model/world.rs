use std::collections::{BTreeMap, HashMap};
use super::types::*;

/// World: top-level container (Task 22)
#[derive(Debug)]
pub struct World {
    pub timelines: BTreeMap<Id, Timeline>,
    pub entities: BTreeMap<Id, Entity>,
    pub relationships: Vec<Relationship>,
    pub type_registry: HashMap<String, TypeDef>,
    pub fn_registry: HashMap<String, FnDef>,
    next_id: Id,
}

impl World {
    pub fn new() -> Self {
        Self {
            timelines: BTreeMap::new(),
            entities: BTreeMap::new(),
            relationships: Vec::new(),
            type_registry: HashMap::new(),
            fn_registry: HashMap::new(),
            next_id: 1,
        }
    }

    pub fn next_id(&mut self) -> Id {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    // --- Entity registry (Task 23) ---

    pub fn entity_by_name(&self, name: &str) -> Option<&Entity> {
        self.entities.values().find(|e| e.name == name)
    }

    pub fn entity_by_id(&self, id: Id) -> Option<&Entity> {
        self.entities.get(&id)
    }

    pub fn entities_of_type(&self, type_id: &str) -> Vec<&Entity> {
        self.entities.values().filter(|e| e.type_id == type_id).collect()
    }

    pub fn entities_on_timeline(&self, timeline_id: Id, range: &TimeRange) -> Vec<&Entity> {
        self.entities.values().filter(|e| {
            e.timeline_appearances.iter().any(|(tid, tr)| {
                *tid == timeline_id && tr.overlaps(range)
            })
        }).collect()
    }

    pub fn add_entity(&mut self, entity: Entity) {
        self.entities.insert(entity.id, entity);
    }

    // --- Relationship graph (Task 24) ---

    pub fn neighbors(&self, entity_id: Id) -> Vec<Id> {
        let mut result = Vec::new();
        for r in &self.relationships {
            if r.source_entity_id == entity_id {
                result.push(r.target_entity_id);
            }
            if r.target_entity_id == entity_id && !r.directed {
                result.push(r.source_entity_id);
            }
        }
        result
    }

    pub fn edges_between(&self, e1: Id, e2: Id) -> Vec<&Relationship> {
        self.relationships.iter().filter(|r| {
            (r.source_entity_id == e1 && r.target_entity_id == e2)
            || (r.source_entity_id == e2 && r.target_entity_id == e1 && !r.directed)
        }).collect()
    }

    pub fn edges_at_time(&self, point: &TimePoint) -> Vec<&Relationship> {
        self.relationships.iter().filter(|r| {
            r.temporal_scope.as_ref().map_or(true, |ts| ts.contains(point))
        }).collect()
    }

    pub fn filter_by_label<'a>(&'a self, label: &str) -> Vec<&'a Relationship> {
        self.relationships.iter().filter(|r| r.label == label).collect()
    }

    pub fn add_relationship(&mut self, rel: Relationship) {
        self.relationships.push(rel);
    }

    // --- Timeline tree (Task 25) ---

    pub fn timeline_by_name(&self, name: &str) -> Option<&Timeline> {
        self.timelines.values().find(|t| t.name == name)
    }

    pub fn children_of(&self, timeline_id: Id) -> Vec<&Timeline> {
        self.timelines.values().filter(|t| t.parent_id == Some(timeline_id)).collect()
    }

    pub fn ancestors_of(&self, timeline_id: Id) -> Vec<Id> {
        let mut result = Vec::new();
        let mut visited = std::collections::HashSet::new();
        let mut current = timeline_id;
        visited.insert(current);
        while let Some(tl) = self.timelines.get(&current) {
            if let Some(pid) = tl.parent_id {
                if !visited.insert(pid) {
                    break; // cycle detected
                }
                result.push(pid);
                current = pid;
            } else {
                break;
            }
        }
        result
    }

    pub fn branches_at(&self, point: &TimePoint) -> Vec<&Timeline> {
        self.timelines.values().filter(|t| {
            t.kind == TimelineKindModel::Branch
            && t.fork_point.as_ref().map_or(false, |(_, fp)| {
                fp.to_ordinal() <= point.to_ordinal()
            })
        }).collect()
    }

    pub fn detect_loops(&self) -> Vec<Id> {
        self.timelines.values()
            .filter(|t| t.kind == TimelineKindModel::Loop)
            .map(|t| t.id)
            .collect()
    }

    pub fn add_timeline(&mut self, timeline: Timeline) {
        let id = timeline.id;
        if let Some(pid) = timeline.parent_id {
            if let Some(parent) = self.timelines.get_mut(&pid) {
                parent.children.push(id);
            }
        }
        self.timelines.insert(id, timeline);
    }

    pub fn add_type(&mut self, typedef: TypeDef) {
        self.type_registry.insert(typedef.name.clone(), typedef);
    }

    pub fn add_fn(&mut self, fndef: FnDef) {
        self.fn_registry.insert(fndef.name.clone(), fndef);
    }
}
