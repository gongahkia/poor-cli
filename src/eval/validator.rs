use crate::model::types::*;
use crate::model::world::World;
use std::collections::HashSet;
/// Validation report
pub struct ValidationReport {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}
pub fn validate(world: &World) -> ValidationReport {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    validate_entity_bounds(world, &mut errors, &mut warnings);
    validate_fork_merge(world, &mut errors);
    validate_loops(world, &mut errors, &mut warnings);
    validate_relationship_temporal_scope(world, &mut errors);
    validate_timeline_cycles(world, &mut errors);
    validate_parallel_consistency(world, &mut warnings);
    ValidationReport { errors, warnings }
}
fn validate_entity_bounds(world: &World, errors: &mut Vec<String>, warnings: &mut Vec<String>) {
    for entity in world.entities.values() {
        for (tid, tr) in &entity.timeline_appearances {
            if let Some(tl) = world.timelines.get(tid) {
                if let (Some(ref tl_start), Some(ref tl_end)) = (&tl.start, &tl.end) {
                    let tl_s = tl_start.to_ordinal();
                    let tl_e = tl_end.to_ordinal();
                    let ent_s = tr.start.to_ordinal();
                    let ent_e = tr.end.to_ordinal();
                    if ent_s < tl_s {
                        errors.push(format!(
                            "entity '{}' appears at {} before timeline '{}' starts at {}",
                            entity.name, ent_s, tl.name, tl_s
                        ));
                    }
                    if ent_e > tl_e {
                        warnings.push(format!(
                            "entity '{}' extends to {} beyond timeline '{}' end at {}",
                            entity.name, ent_e, tl.name, tl_e
                        ));
                    }
                }
            }
        }
    }
}
fn validate_fork_merge(world: &World, errors: &mut Vec<String>) {
    for tl in world.timelines.values() {
        if let Some((parent_id, ref fork_point)) = tl.fork_point {
            if let Some(parent) = world.timelines.get(&parent_id) {
                if let (Some(ref ps), Some(ref pe)) = (&parent.start, &parent.end) {
                    let fp = fork_point.to_ordinal();
                    if fp < ps.to_ordinal() || fp > pe.to_ordinal() {
                        errors.push(format!(
                            "fork point of '{}' at {} is outside parent '{}' bounds",
                            tl.name, fp, parent.name
                        ));
                    }
                }
            }
        }
        if let Some((target_id, ref merge_point)) = tl.merge_point {
            if let Some(target) = world.timelines.get(&target_id) {
                if let (Some(ref ts), Some(ref te)) = (&target.start, &target.end) {
                    let mp = merge_point.to_ordinal();
                    if mp < ts.to_ordinal() || mp > te.to_ordinal() {
                        errors.push(format!(
                            "merge of '{}' into '{}' at {} is outside target bounds",
                            tl.name, target.name, mp
                        ));
                    }
                }
            }
        }
    }
}
fn validate_loops(world: &World, errors: &mut Vec<String>, warnings: &mut Vec<String>) {
    for tl in world.timelines.values() {
        if tl.kind == TimelineKindModel::Loop {
            if let Some(ref lc) = tl.loop_config {
                if lc.count <= 0 {
                    warnings.push(format!(
                        "loop '{}' has non-positive iteration count {}",
                        tl.name, lc.count
                    ));
                }
                if lc.entry_time.to_ordinal() >= lc.exit_time.to_ordinal() {
                    errors.push(format!(
                        "loop '{}' entry >= exit (infinite loop potential)",
                        tl.name
                    ));
                }
            } else {
                warnings.push(format!(
                    "loop '{}' has no loop config (no exit condition)",
                    tl.name
                ));
            }
        }
    }
}
/// Verify relationship temporal_scope overlaps with source/target entity ranges
fn validate_relationship_temporal_scope(world: &World, errors: &mut Vec<String>) {
    for rel in &world.relationships {
        if let Some(ref scope) = rel.temporal_scope {
            let src_name = world
                .entity_by_id(rel.source_entity_id)
                .map(|e| e.name.as_str())
                .unwrap_or("?");
            let tgt_name = world
                .entity_by_id(rel.target_entity_id)
                .map(|e| e.name.as_str())
                .unwrap_or("?");
            if let Some(src) = world.entity_by_id(rel.source_entity_id) {
                let src_overlaps = src
                    .timeline_appearances
                    .iter()
                    .any(|(_, tr)| tr.overlaps(scope));
                if !src_overlaps {
                    errors.push(format!("relationship '{}'-[{}]->'{}' temporal scope doesn't overlap with source entity's time range", src_name, rel.label, tgt_name));
                }
            }
            if let Some(tgt) = world.entity_by_id(rel.target_entity_id) {
                let tgt_overlaps = tgt
                    .timeline_appearances
                    .iter()
                    .any(|(_, tr)| tr.overlaps(scope));
                if !tgt_overlaps {
                    errors.push(format!("relationship '{}'-[{}]->'{}' temporal scope doesn't overlap with target entity's time range", src_name, rel.label, tgt_name));
                }
            }
        }
    }
}
/// Detect cycles in timeline hierarchy
fn validate_timeline_cycles(world: &World, errors: &mut Vec<String>) {
    for tl in world.timelines.values() {
        let mut visited = HashSet::new();
        let mut current = tl.id;
        visited.insert(current);
        while let Some(parent_tl) = world.timelines.get(&current) {
            if let Some(pid) = parent_tl.parent_id {
                if !visited.insert(pid) {
                    errors.push(format!(
                        "timeline hierarchy cycle detected involving '{}'",
                        tl.name
                    ));
                    break;
                }
                current = pid;
            } else {
                break;
            }
        }
    }
}
/// Warn if entities on parallel sibling timelines have overlapping time ranges
fn validate_parallel_consistency(world: &World, warnings: &mut Vec<String>) {
    let parallels: Vec<_> = world
        .timelines
        .values()
        .filter(|t| t.kind == TimelineKindModel::Parallel)
        .collect();
    for i in 0..parallels.len() {
        for j in (i + 1)..parallels.len() {
            let a = parallels[i];
            let b = parallels[j];
            if a.parent_id != b.parent_id || a.parent_id.is_none() {
                continue;
            }
            for ea in world.entities.values() {
                for (tid_a, tr_a) in &ea.timeline_appearances {
                    if *tid_a != a.id {
                        continue;
                    }
                    for eb in world.entities.values() {
                        for (tid_b, tr_b) in &eb.timeline_appearances {
                            if *tid_b != b.id {
                                continue;
                            }
                            if ea.name == eb.name && tr_a.overlaps(tr_b) {
                                warnings.push(format!("entity '{}' appears on parallel timelines '{}' and '{}' with overlapping ranges (narrative conflict)", ea.name, a.name, b.name));
                            }
                        }
                    }
                }
            }
        }
    }
}
