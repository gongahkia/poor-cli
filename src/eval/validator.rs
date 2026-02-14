use crate::model::world::World;
use crate::model::types::*;

/// Temporal consistency validator (Task 44)
pub struct ValidationReport {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

pub fn validate_temporal_consistency(world: &World) -> ValidationReport {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();

    // Check entities appear within their timeline bounds
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

    // Check fork points are within parent bounds
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
    }

    // Check merge of non-overlapping timelines
    for tl in world.timelines.values() {
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

    // Check time loop paradox detection (Task 45)
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

    ValidationReport { errors, warnings }
}
