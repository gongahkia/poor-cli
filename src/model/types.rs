use chrono::NaiveDate;
use std::collections::HashMap;

pub type Id = u64;

/// Timeline kind (Task 17)
#[derive(Debug, Clone, PartialEq)]
pub enum TimelineKindModel {
    Linear,
    Branch,
    Parallel,
    Loop,
    Nested,
}

/// Event marker on a timeline
#[derive(Debug, Clone)]
pub struct EventMarker {
    pub time: TimePoint,
    pub label: String,
    pub entity_id: Option<Id>,
}

/// Loop configuration
#[derive(Debug, Clone)]
pub struct LoopConfig {
    pub count: i64,
    pub entry_time: TimePoint,
    pub exit_time: TimePoint,
}

/// Timeline struct (Task 17)
#[derive(Debug, Clone)]
pub struct Timeline {
    pub id: Id,
    pub name: String,
    pub kind: TimelineKindModel,
    pub start: Option<TimePoint>,
    pub end: Option<TimePoint>,
    pub parent_id: Option<Id>,
    pub fork_point: Option<(Id, TimePoint)>,
    pub merge_point: Option<(Id, TimePoint)>,
    pub loop_config: Option<LoopConfig>,
    pub children: Vec<Id>,
    pub event_markers: Vec<EventMarker>,
}

/// Entity struct (Task 18)
#[derive(Debug, Clone)]
pub struct Entity {
    pub id: Id,
    pub name: String,
    pub type_id: String,
    pub attributes: HashMap<String, Value>,
    pub timeline_appearances: Vec<(Id, TimeRange)>,
    pub lifecycle_events: Vec<LifecycleEvent>,
}

#[derive(Debug, Clone)]
pub struct LifecycleEvent {
    pub kind: LifecycleKind,
    pub time: TimePoint,
    pub description: String,
}

/// Built-in lifecycle event kinds (Task 36)
#[derive(Debug, Clone, PartialEq)]
pub enum LifecycleKind {
    Born,
    Died,
    Created,
    Destroyed,
    Transformed,
    Custom(String),
}

impl LifecycleKind {
    pub fn from_str(s: &str) -> Self {
        match s {
            "born" => Self::Born,
            "died" => Self::Died,
            "created" => Self::Created,
            "destroyed" => Self::Destroyed,
            "transformed" => Self::Transformed,
            other => Self::Custom(other.to_string()),
        }
    }

    pub fn label(&self) -> &str {
        match self {
            Self::Born => "born",
            Self::Died => "died",
            Self::Created => "created",
            Self::Destroyed => "destroyed",
            Self::Transformed => "transformed",
            Self::Custom(s) => s,
        }
    }
}

/// Faction/group entity type (Task 37)
#[derive(Debug, Clone)]
pub struct FactionMembership {
    pub entity_id: Id,
    pub time_range: TimeRange,
    pub role: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct FactionData {
    pub members: Vec<FactionMembership>,
}

/// Location entity type (Task 38)
#[derive(Debug, Clone, Default)]
pub struct LocationData {
    pub coordinates: Option<(f64, f64)>,
    pub occupants: Vec<(Id, TimeRange)>,
}

/// Artifact entity type (Task 39)
#[derive(Debug, Clone)]
pub struct ArtifactOwnership {
    pub entity_id: Id,
    pub time_range: TimeRange,
}

#[derive(Debug, Clone, Default)]
pub struct ArtifactData {
    pub owners: Vec<ArtifactOwnership>,
}

/// Relationship struct (Task 19)
#[derive(Debug, Clone)]
pub struct Relationship {
    pub id: Id,
    pub source_entity_id: Id,
    pub target_entity_id: Id,
    pub label: String,
    pub directed: bool,
    pub temporal_scope: Option<TimeRange>,
    pub attributes: HashMap<String, Value>,
}

/// TimePoint enum (Task 20)
#[derive(Debug, Clone)]
pub enum TimePoint {
    Absolute(NaiveDate),
    Relative {
        anchor: String,
        offset_days: i64,
    },
    Fuzzy {
        center: NaiveDate,
        radius_days: i64,
    },
    EraRef {
        timeline: String,
        era: String,
        point: String,
    },
    Abstract(i64),
}

impl TimePoint {
    pub fn offset_days(&self, days: i64) -> TimePoint {
        match self {
            TimePoint::Absolute(d) => {
                let new_d = *d + chrono::Duration::days(days);
                TimePoint::Absolute(new_d)
            }
            TimePoint::Abstract(n) => TimePoint::Abstract(n + days),
            TimePoint::Fuzzy {
                center,
                radius_days,
            } => TimePoint::Fuzzy {
                center: *center + chrono::Duration::days(days),
                radius_days: *radius_days,
            },
            other => other.clone(), // relative/era refs can't easily offset
        }
    }
    pub fn to_ordinal(&self) -> i64 {
        match self {
            TimePoint::Absolute(d) => {
                let epoch = chrono::NaiveDate::from_ymd_opt(1, 1, 1).unwrap();
                d.signed_duration_since(epoch).num_days()
            }
            TimePoint::Abstract(n) => *n,
            TimePoint::Fuzzy { center, .. } => {
                let epoch = chrono::NaiveDate::from_ymd_opt(1, 1, 1).unwrap();
                center.signed_duration_since(epoch).num_days()
            }
            TimePoint::Relative { offset_days, .. } => *offset_days,
            TimePoint::EraRef { .. } => 0,
        }
    }

    /// Resolve EraRef to an absolute ordinal using World context.
    /// For non-EraRef variants, delegates to to_ordinal().
    pub fn to_ordinal_in_world(&self, world: &crate::model::world::World) -> i64 {
        match self {
            TimePoint::EraRef {
                timeline,
                era,
                point,
            } => {
                let tl = match world.timeline_by_name(timeline) {
                    Some(t) => t,
                    None => return 0,
                };
                let matching: Vec<&EventMarker> = tl
                    .event_markers
                    .iter()
                    .filter(|m| m.label == *era)
                    .collect();
                if matching.is_empty() {
                    return tl.start.as_ref().map_or(0, |s| s.to_ordinal());
                }
                match point.as_str() {
                    "start" => matching.first().unwrap().time.to_ordinal(),
                    "end" => matching.last().unwrap().time.to_ordinal(),
                    _ => {
                        if let Ok(offset) = point.parse::<i64>() {
                            matching.first().unwrap().time.to_ordinal() + offset
                        } else {
                            matching.first().unwrap().time.to_ordinal()
                        }
                    }
                }
            }
            _ => self.to_ordinal(),
        }
    }
}

/// TimeRange struct (Task 21)
#[derive(Debug, Clone)]
pub struct TimeRange {
    pub start: TimePoint,
    pub end: TimePoint,
    pub inclusive_end: bool,
}

impl TimeRange {
    pub fn contains(&self, point: &TimePoint) -> bool {
        let p = point.to_ordinal();
        let s = self.start.to_ordinal();
        let e = self.end.to_ordinal();
        if self.inclusive_end {
            p >= s && p <= e
        } else {
            p >= s && p < e
        }
    }

    pub fn overlaps(&self, other: &TimeRange) -> bool {
        self.start.to_ordinal() < other.end.to_ordinal()
            && other.start.to_ordinal() < self.end.to_ordinal()
    }

    pub fn intersection(&self, other: &TimeRange) -> Option<TimeRange> {
        let s = self.start.to_ordinal().max(other.start.to_ordinal());
        let e = self.end.to_ordinal().min(other.end.to_ordinal());
        if s < e {
            Some(TimeRange {
                start: TimePoint::Abstract(s),
                end: TimePoint::Abstract(e),
                inclusive_end: false,
            })
        } else {
            None
        }
    }

    pub fn union(&self, other: &TimeRange) -> TimeRange {
        TimeRange {
            start: TimePoint::Abstract(self.start.to_ordinal().min(other.start.to_ordinal())),
            end: TimePoint::Abstract(self.end.to_ordinal().max(other.end.to_ordinal())),
            inclusive_end: self.inclusive_end || other.inclusive_end,
        }
    }
}

/// Runtime value type
#[derive(Debug, Clone)]
pub enum Value {
    Int(i64),
    Float(f64),
    String(String),
    Bool(bool),
    Date(TimePoint),
    Duration(i64),
    Entity(Id),
    Timeline(Id),
    List(Vec<Value>),
    Closure {
        params: Vec<crate::lang::ast::Param>,
        body: Box<crate::lang::ast::Spanned<crate::lang::ast::Expr>>,
        captured: Vec<HashMap<String, Value>>,
    },
    Null,
}

impl std::fmt::Display for Value {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Value::Int(n) => write!(f, "{}", n),
            Value::Float(n) => write!(f, "{}", n),
            Value::String(s) => write!(f, "{}", s),
            Value::Bool(b) => write!(f, "{}", b),
            Value::Date(tp) => write!(f, "{:?}", tp),
            Value::Duration(d) => write!(f, "{}days", d),
            Value::Entity(id) => write!(f, "entity#{}", id),
            Value::Timeline(id) => write!(f, "timeline#{}", id),
            Value::List(items) => write!(
                f,
                "[{}]",
                items
                    .iter()
                    .map(|i| format!("{}", i))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            Value::Closure { .. } => write!(f, "<closure>"),
            Value::Null => write!(f, "null"),
        }
    }
}

/// Type definition
#[derive(Debug, Clone)]
pub struct TypeDef {
    pub name: String,
    pub parent: Option<String>,
    pub fields: Vec<TypeFieldDef>,
    pub meta: HashMap<String, Value>,
}

#[derive(Debug, Clone)]
pub struct TypeFieldDef {
    pub name: String,
    pub type_name: String,
    pub optional: bool,
}

/// Function definition
#[derive(Debug, Clone)]
pub struct FnDef {
    pub name: String,
    pub params: Vec<(String, String)>,
    pub return_type: Option<String>,
    pub body: crate::lang::ast::Block,
}
