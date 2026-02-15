use std::collections::HashMap;
use crate::model::types::*;
use crate::model::world::World;

/// Viewport model (Task 47)
#[derive(Debug, Clone)]
pub struct Viewport {
    pub time_start: f64,
    pub time_end: f64,
    pub lane_start: usize,
    pub lane_end: usize,
    pub scale: f64,
}

impl Viewport {
    pub fn new(time_start: f64, time_end: f64, lanes: usize) -> Self {
        Self { time_start, time_end, lane_start: 0, lane_end: lanes, scale: 1.0 }
    }

    pub fn pan(&mut self, dt: f64, dl: i32) {
        self.time_start += dt;
        self.time_end += dt;
        self.lane_start = (self.lane_start as i32 + dl).max(0) as usize;
        self.lane_end = (self.lane_end as i32 + dl).max(0) as usize;
    }

    pub fn zoom(&mut self, factor: f64) {
        let center = (self.time_start + self.time_end) / 2.0;
        let half = (self.time_end - self.time_start) / 2.0 / factor;
        self.time_start = center - half;
        self.time_end = center + half;
        self.scale *= factor;
    }

    pub fn focus(&mut self, time: f64, lane: usize) {
        let half_t = (self.time_end - self.time_start) / 2.0;
        let half_l = (self.lane_end - self.lane_start) / 2;
        self.time_start = time - half_t;
        self.time_end = time + half_t;
        self.lane_start = lane.saturating_sub(half_l);
        self.lane_end = lane + half_l;
    }
}

/// Laid-out entity bar
#[derive(Debug, Clone)]
pub struct LayoutEntity {
    pub entity_id: Id,
    pub name: String,
    pub entity_type: String,
    pub lane: usize,
    pub x_start: f64,
    pub x_end: f64,
    pub timeline_id: Id,
}

/// Laid-out relationship edge
#[derive(Debug, Clone)]
pub struct LayoutEdge {
    pub source_lane: usize,
    pub target_lane: usize,
    pub source_x: f64,
    pub target_x: f64,
    pub label: String,
    pub directed: bool,
}

/// Laid-out timeline region
#[derive(Debug, Clone)]
pub struct LayoutTimeline {
    pub timeline_id: Id,
    pub name: String,
    pub kind: TimelineKindModel,
    pub x_start: f64,
    pub x_end: f64,
    pub lane_start: usize,
    pub lane_end: usize,
    pub is_loop: bool,
    pub loop_count: Option<i64>,
}

/// Branch/merge connector
#[derive(Debug, Clone)]
pub struct LayoutConnector {
    pub from_x: f64,
    pub from_lane: usize,
    pub to_x: f64,
    pub to_lane: usize,
    pub kind: ConnectorKind,
}

#[derive(Debug, Clone)]
pub enum ConnectorKind {
    Fork,
    Merge,
}

/// Time axis tick
#[derive(Debug, Clone)]
pub struct TickMark {
    pub x: f64,
    pub label: String,
}

/// Complete layout output
#[derive(Debug)]
pub struct Layout {
    pub entities: Vec<LayoutEntity>,
    pub edges: Vec<LayoutEdge>,
    pub timelines: Vec<LayoutTimeline>,
    pub connectors: Vec<LayoutConnector>,
    pub ticks: Vec<TickMark>,
    pub viewport: Viewport,
    pub total_lanes: usize,
    pub total_width: f64,
}

/// Compute layout from World (Tasks 38-47)
pub fn compute_layout(world: &World) -> Layout {
    let mut entities = Vec::new();
    let mut edges = Vec::new();
    let mut timelines_layout: Vec<LayoutTimeline> = Vec::new();
    let mut connectors = Vec::new();
    let mut ticks = Vec::new();

    // Collect time bounds
    let mut global_min: f64 = f64::MAX;
    let mut global_max: f64 = f64::MIN;

    // Assign lanes to entities (Task 39 - swim lane allocation)
    let mut lane_map: HashMap<Id, usize> = HashMap::new();
    let mut current_lane: usize = 0;

    // Group entities by timeline
    let mut timeline_entities: HashMap<Id, Vec<Id>> = HashMap::new();
    for entity in world.entities.values() {
        for (tid, _) in &entity.timeline_appearances {
            timeline_entities.entry(*tid).or_default().push(entity.id);
        }
    }
    // Entities with no timeline appearances
    for entity in world.entities.values() {
        if entity.timeline_appearances.is_empty() {
            timeline_entities.entry(0).or_default().push(entity.id);
        }
    }

    // Layout each timeline region (Task 42 - parallel stacking)
    for tl in world.timelines.values() {
        let tl_lane_start = current_lane;
        let ent_ids = timeline_entities.get(&tl.id).cloned().unwrap_or_default();

        let tl_x_start = tl.start.as_ref().map(|t| t.to_ordinal() as f64).unwrap_or(0.0);
        let tl_x_end = tl.end.as_ref().map(|t| t.to_ordinal() as f64).unwrap_or(100.0);

        global_min = global_min.min(tl_x_start);
        global_max = global_max.max(tl_x_end);

        for eid in &ent_ids {
            if !lane_map.contains_key(eid) {
                // Lane compaction: find a reusable lane with no time overlap
                let entity_range = world.entity_by_id(*eid).and_then(|e| {
                    e.timeline_appearances.iter()
                        .find(|(tid, _)| *tid == tl.id)
                        .map(|(_, tr)| (tr.start.to_ordinal() as f64, tr.end.to_ordinal() as f64))
                });
                let reused = entity_range.and_then(|(es, ee)| {
                    find_reusable_lane(&entities, tl_lane_start, current_lane, es, ee)
                });
                let lane = reused.unwrap_or_else(|| {
                    let l = current_lane;
                    current_lane += 1;
                    l
                });
                lane_map.insert(*eid, lane);
            }
        }

        let tl_lane_end = current_lane.max(tl_lane_start + 1);

        // Layout entity bars (Task 38 - horizontal time axis)
        for eid in &ent_ids {
            if let Some(entity) = world.entity_by_id(*eid) {
                let lane = *lane_map.get(eid).unwrap_or(&0);
                for (tid, tr) in &entity.timeline_appearances {
                    if *tid == tl.id {
                        let x_start = tr.start.to_ordinal() as f64;
                        let x_end = tr.end.to_ordinal() as f64;
                        global_min = global_min.min(x_start);
                        global_max = global_max.max(x_end);
                        entities.push(LayoutEntity {
                            entity_id: entity.id,
                            name: entity.name.clone(),
                            entity_type: entity.type_id.clone(),
                            lane,
                            x_start,
                            x_end,
                            timeline_id: tl.id,
                        });
                    }
                }
            }
        }

        // Branch connector (Task 40) - use actual parent lane
        if let Some((parent_id, ref fp)) = tl.fork_point {
            let parent_lane = timelines_layout.iter()
                .find(|lt| lt.timeline_id == parent_id)
                .map(|lt| lt.lane_start)
                .unwrap_or(tl_lane_start.saturating_sub(1));
            connectors.push(LayoutConnector {
                from_x: fp.to_ordinal() as f64,
                from_lane: parent_lane,
                to_x: fp.to_ordinal() as f64,
                to_lane: tl_lane_start,
                kind: ConnectorKind::Fork,
            });
        }

        // Merge connector (Task 41) - use actual target lane
        if let Some((target_id, ref mp)) = tl.merge_point {
            let target_lane = timelines_layout.iter()
                .find(|lt| lt.timeline_id == target_id)
                .map(|lt| lt.lane_start)
                .unwrap_or(tl_lane_start.saturating_sub(1));
            connectors.push(LayoutConnector {
                from_x: mp.to_ordinal() as f64,
                from_lane: tl_lane_end.saturating_sub(1),
                to_x: mp.to_ordinal() as f64,
                to_lane: target_lane,
                kind: ConnectorKind::Merge,
            });
        }

        // Timeline region (Task 43 - loop layout)
        let is_loop = tl.kind == TimelineKindModel::Loop;
        timelines_layout.push(LayoutTimeline {
            timeline_id: tl.id,
            name: tl.name.clone(),
            kind: tl.kind.clone(),
            x_start: tl_x_start,
            x_end: tl_x_end,
            lane_start: tl_lane_start,
            lane_end: tl_lane_end,
            is_loop,
            loop_count: tl.loop_config.as_ref().map(|lc| lc.count),
        });
    }

    // Handle entities with no timeline
    let orphan_ids = timeline_entities.get(&0).cloned().unwrap_or_default();
    for eid in &orphan_ids {
        if !lane_map.contains_key(eid) {
            lane_map.insert(*eid, current_lane);
            current_lane += 1;
        }
        if let Some(entity) = world.entity_by_id(*eid) {
            entities.push(LayoutEntity {
                entity_id: entity.id,
                name: entity.name.clone(),
                entity_type: entity.type_id.clone(),
                lane: *lane_map.get(eid).unwrap_or(&0),
                x_start: global_min,
                x_end: global_max,
                timeline_id: 0,
            });
        }
    }

    if global_min == f64::MAX { global_min = 0.0; }
    if global_max == f64::MIN { global_max = 100.0; }

    // Relationship edge routing (Task 45)
    for rel in &world.relationships {
        let src_lane = lane_map.get(&rel.source_entity_id).copied().unwrap_or(0);
        let tgt_lane = lane_map.get(&rel.target_entity_id).copied().unwrap_or(0);

        let src_x = rel.temporal_scope.as_ref()
            .map(|ts| ts.start.to_ordinal() as f64)
            .unwrap_or((global_min + global_max) / 2.0);
        let tgt_x = rel.temporal_scope.as_ref()
            .map(|ts| ts.end.to_ordinal() as f64)
            .unwrap_or(src_x);

        edges.push(LayoutEdge {
            source_lane: src_lane,
            target_lane: tgt_lane,
            source_x: src_x,
            target_x: tgt_x,
            label: rel.label.clone(),
            directed: rel.directed,
        });
    }

    // Generate tick marks (Task 38)
    let range = global_max - global_min;
    let tick_interval = if range <= 0.0 { 1.0 } else {
        let approx = range / 10.0;
        10.0_f64.powf(approx.log10().floor())
    };
    let mut tick_pos = (global_min / tick_interval).floor() * tick_interval;
    while tick_pos <= global_max {
        ticks.push(TickMark {
            x: tick_pos,
            label: format!("{}", tick_pos as i64),
        });
        tick_pos += tick_interval;
    }

    let total_lanes = current_lane.max(1);
    let total_width = global_max - global_min;

    // Label collision resolution (Task 46) - simple stagger
    resolve_label_collisions(&mut entities);

    let viewport = Viewport::new(global_min, global_max, total_lanes);

    Layout {
        entities,
        edges,
        timelines: timelines_layout,
        connectors,
        ticks,
        viewport,
        total_lanes,
        total_width,
    }
}

/// Lane compaction: find a lane in [lane_start..lane_end) that has no overlapping time range
fn find_reusable_lane(
    entities: &[LayoutEntity],
    lane_start: usize,
    lane_end: usize,
    x_start: f64,
    x_end: f64,
) -> Option<usize> {
    for lane in lane_start..lane_end {
        let has_overlap = entities.iter().any(|e| {
            e.lane == lane && e.x_start < x_end && e.x_end > x_start
        });
        if !has_overlap {
            return Some(lane);
        }
    }
    None
}

/// Label collision resolution: detect overlapping labels and shift them vertically
fn resolve_label_collisions(entities: &mut [LayoutEntity]) {
    // Sort by lane then x_start
    entities.sort_by(|a, b| {
        a.lane.cmp(&b.lane)
            .then(a.x_start.partial_cmp(&b.x_start).unwrap_or(std::cmp::Ordering::Equal))
    });

    // Detect overlapping entities on the same lane and nudge the shorter one
    let label_width_estimate = 12.0; // approximate character width in time units
    let len = entities.len();
    for i in 0..len {
        for j in (i + 1)..len {
            if entities[i].lane != entities[j].lane { break; }
            let i_label_end = entities[i].x_end + label_width_estimate;
            if entities[j].x_start < i_label_end {
                // Collision: offset the name with a leader marker
                entities[j].name = format!("  {}", entities[j].name);
            } else {
                break;
            }
        }
    }
}
