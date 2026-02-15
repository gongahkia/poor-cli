use crate::model::types::Value;
use std::collections::HashMap;

/// Variable environment as stack of HashMap frames (Task 26)
#[derive(Debug)]
pub struct Environment {
    frames: Vec<HashMap<String, Value>>,
}

impl Environment {
    pub fn new() -> Self {
        Self {
            frames: vec![HashMap::new()],
        }
    }

    pub fn push_scope(&mut self) {
        self.frames.push(HashMap::new());
    }

    pub fn pop_scope(&mut self) {
        if self.frames.len() > 1 {
            self.frames.pop();
        }
    }

    pub fn bind(&mut self, name: String, value: Value) {
        if let Some(frame) = self.frames.last_mut() {
            frame.insert(name, value);
        }
    }

    pub fn lookup(&self, name: &str) -> Option<&Value> {
        for frame in self.frames.iter().rev() {
            if let Some(v) = frame.get(name) {
                return Some(v);
            }
        }
        None
    }

    pub fn snapshot(&self) -> Vec<HashMap<String, Value>> {
        self.frames.clone()
    }
    pub fn with_snapshot(&mut self, snap: Vec<HashMap<String, Value>>) {
        self.frames = snap;
    }
    pub fn set(&mut self, name: &str, value: Value) -> bool {
        for frame in self.frames.iter_mut().rev() {
            if frame.contains_key(name) {
                frame.insert(name.to_string(), value);
                return true;
            }
        }
        false
    }
}
