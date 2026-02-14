use std::collections::{HashSet, HashMap};
use crate::layout::engine::Layout;
use crate::model::types::Id;

/// Input mode
#[derive(Debug, Clone, PartialEq)]
pub enum InputMode {
    Normal,
    Search,
    Filter,
    Help,
    BranchNav,
    CommandPalette,
    CompareSelect,
}

/// Viewport snapshot for undo/redo (Task 51)
#[derive(Debug, Clone)]
struct ViewState {
    time_start: f64,
    time_end: f64,
    lane_start: usize,
    lane_end: usize,
    scale: f64,
    selected: Option<Id>,
}

/// App state (Tasks 48, 54-64, 109-112)
pub struct App {
    pub layout: Layout,
    pub input_mode: InputMode,
    pub selected_entity: Option<Id>,
    pub should_quit: bool,
    pub search_query: String,
    pub status_message: String,
    pub file_path: String,
    // Time scrubber (Task 54)
    pub time_cursor: f64,
    pub scrubber_playing: bool,
    // Filters (Task 55)
    pub type_filters: HashSet<String>,
    pub label_filters: HashSet<String>,
    // Layer toggle (Task 56)
    pub active_layer: usize,
    pub layer_names: Vec<String>,
    // Undo/redo (Task 51)
    undo_stack: Vec<ViewState>,
    redo_stack: Vec<ViewState>,
    // Bookmarks (Task 53/112)
    bookmarks: HashMap<u8, ViewState>,
    // Drill-down stack (Task 7)
    drill_stack: Vec<ViewState>,
    // Command palette (Task 52)
    pub palette_query: String,
    pub available_commands: Vec<(&'static str, &'static str)>,
    // Timeline comparison (Task 50)
    pub compare_mode: bool,
    pub compare_timeline_idx: Option<usize>,
}

impl App {
    pub fn new(layout: Layout, file_path: String) -> Self {
        let time_cursor = layout.viewport.time_start;
        let mut type_set = HashSet::new();
        let mut label_set = HashSet::new();
        for ent in &layout.entities {
            type_set.insert(ent.entity_type.clone());
        }
        for edge in &layout.edges {
            if !edge.label.is_empty() {
                label_set.insert(edge.label.clone());
            }
        }
        let mut layer_names = vec!["All".to_string()];
        for l in &label_set {
            layer_names.push(l.clone());
        }

        Self {
            layout,
            input_mode: InputMode::Normal,
            selected_entity: None,
            should_quit: false,
            search_query: String::new(),
            status_message: String::new(),
            file_path,
            time_cursor,
            scrubber_playing: false,
            type_filters: type_set,
            label_filters: label_set,
            active_layer: 0,
            layer_names,
            undo_stack: Vec::new(),
            redo_stack: Vec::new(),
            bookmarks: HashMap::new(),
            drill_stack: Vec::new(),
            palette_query: String::new(),
            available_commands: vec![
                ("quit", "Exit the application"),
                ("search", "Search entities by name"),
                ("filter", "Open filter panel"),
                ("help", "Show keybindings"),
                ("branches", "Browse timeline branches"),
                ("zoom-in", "Zoom in"),
                ("zoom-out", "Zoom out"),
                ("reset", "Reset viewport"),
                ("play", "Play/pause time scrubber"),
                ("next-entity", "Select next entity"),
                ("bookmark", "Save bookmark"),
                ("undo", "Undo last viewport change"),
                ("redo", "Redo viewport change"),
            ],
            compare_mode: false,
            compare_timeline_idx: None,
        }
    }

    fn save_view_state(&mut self) {
        let vp = &self.layout.viewport;
        self.undo_stack.push(ViewState {
            time_start: vp.time_start,
            time_end: vp.time_end,
            lane_start: vp.lane_start,
            lane_end: vp.lane_end,
            scale: vp.scale,
            selected: self.selected_entity,
        });
        self.redo_stack.clear();
    }

    fn restore_view_state(&mut self, state: ViewState) {
        self.layout.viewport.time_start = state.time_start;
        self.layout.viewport.time_end = state.time_end;
        self.layout.viewport.lane_start = state.lane_start;
        self.layout.viewport.lane_end = state.lane_end;
        self.layout.viewport.scale = state.scale;
        self.selected_entity = state.selected;
    }

    /// Keyboard navigation (Tasks 52, 54-64, 110-112)
    pub fn handle_key(&mut self, key: crossterm::event::KeyEvent) {
        use crossterm::event::{KeyCode, KeyModifiers};
        match self.input_mode {
            InputMode::Normal => match key.code {
                KeyCode::Char('q') => self.should_quit = true,
                KeyCode::Char('h') | KeyCode::Left => {
                    self.save_view_state();
                    self.layout.viewport.pan(-5.0, 0);
                }
                KeyCode::Char('l') | KeyCode::Right => {
                    self.save_view_state();
                    self.layout.viewport.pan(5.0, 0);
                }
                KeyCode::Char('k') | KeyCode::Up => {
                    self.save_view_state();
                    self.layout.viewport.pan(0.0, -1);
                }
                KeyCode::Char('j') | KeyCode::Down => {
                    self.save_view_state();
                    self.layout.viewport.pan(0.0, 1);
                }
                KeyCode::Char('+') | KeyCode::Char('=') => {
                    self.save_view_state();
                    self.layout.viewport.zoom(1.2);
                }
                KeyCode::Char('-') => {
                    self.save_view_state();
                    self.layout.viewport.zoom(0.8);
                }
                KeyCode::Tab => self.cycle_selection(),
                KeyCode::Enter => self.drill_down(),
                KeyCode::Backspace => self.drill_up(),
                KeyCode::Esc => {
                    self.selected_entity = None;
                    self.status_message = "Deselected".to_string();
                }
                KeyCode::Char('?') => self.input_mode = InputMode::Help,
                KeyCode::Char('/') => {
                    self.input_mode = InputMode::Search;
                    self.search_query.clear();
                }
                KeyCode::Char('f') => self.input_mode = InputMode::Filter,
                KeyCode::Char('b') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    // Bookmark current view (Task 112)
                    let idx = (self.bookmarks.len() as u8) + 1;
                    if idx <= 9 {
                        let vp = &self.layout.viewport;
                        self.bookmarks.insert(idx, ViewState {
                            time_start: vp.time_start, time_end: vp.time_end,
                            lane_start: vp.lane_start, lane_end: vp.lane_end,
                            scale: vp.scale, selected: self.selected_entity,
                        });
                        self.status_message = format!("Bookmark {} saved", idx);
                    }
                }
                KeyCode::Char(c @ '1'..='9') => {
                    let idx = c as u8 - b'0';
                    if let Some(state) = self.bookmarks.get(&idx).cloned() {
                        self.restore_view_state(state);
                        self.status_message = format!("Jumped to bookmark {}", idx);
                    }
                }
                KeyCode::Char('z') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    // Undo (Task 110)
                    if let Some(state) = self.undo_stack.pop() {
                        let cur = ViewState {
                            time_start: self.layout.viewport.time_start,
                            time_end: self.layout.viewport.time_end,
                            lane_start: self.layout.viewport.lane_start,
                            lane_end: self.layout.viewport.lane_end,
                            scale: self.layout.viewport.scale,
                            selected: self.selected_entity,
                        };
                        self.redo_stack.push(cur);
                        self.restore_view_state(state);
                        self.status_message = "Undo".to_string();
                    }
                }
                KeyCode::Char('y') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    // Redo (Task 110)
                    if let Some(state) = self.redo_stack.pop() {
                        let cur = ViewState {
                            time_start: self.layout.viewport.time_start,
                            time_end: self.layout.viewport.time_end,
                            lane_start: self.layout.viewport.lane_start,
                            lane_end: self.layout.viewport.lane_end,
                            scale: self.layout.viewport.scale,
                            selected: self.selected_entity,
                        };
                        self.undo_stack.push(cur);
                        self.restore_view_state(state);
                        self.status_message = "Redo".to_string();
                    }
                }
                // Time scrubber (Task 54)
                KeyCode::Char('[') => {
                    self.time_cursor -= 1.0;
                    self.status_message = format!("Time: {:.0}", self.time_cursor);
                }
                KeyCode::Char(']') => {
                    self.time_cursor += 1.0;
                    self.status_message = format!("Time: {:.0}", self.time_cursor);
                }
                KeyCode::Char(' ') => {
                    self.scrubber_playing = !self.scrubber_playing;
                    self.status_message = if self.scrubber_playing { "▶ Playing".into() } else { "⏸ Paused".into() };
                }
                // Layer toggle (Task 56)
                KeyCode::Char('v') => {
                    self.active_layer = (self.active_layer + 1) % self.layer_names.len();
                    self.status_message = format!("Layer: {}", self.layer_names[self.active_layer]);
                }
                // Branch nav (Task 58)
                KeyCode::Char('B') => self.input_mode = InputMode::BranchNav,
                // Command palette (Task 52)
                KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    self.input_mode = InputMode::CommandPalette;
                    self.palette_query.clear();
                }
                // Timeline comparison (Task 50)
                KeyCode::Char('C') => {
                    if self.layout.timelines.len() >= 2 {
                        self.input_mode = InputMode::CompareSelect;
                    } else {
                        self.status_message = "Need 2+ timelines to compare".into();
                    }
                }
                _ => {}
            },
            InputMode::Search => match key.code {
                KeyCode::Esc => self.input_mode = InputMode::Normal,
                KeyCode::Enter => {
                    self.jump_to_search();
                    self.input_mode = InputMode::Normal;
                }
                KeyCode::Char(c) => self.search_query.push(c),
                KeyCode::Backspace => { self.search_query.pop(); }
                _ => {}
            },
            InputMode::Help => match key.code {
                KeyCode::Char('?') | KeyCode::Esc => self.input_mode = InputMode::Normal,
                _ => {}
            },
            InputMode::Filter => match key.code {
                KeyCode::Esc => self.input_mode = InputMode::Normal,
                KeyCode::Char('t') => {
                    // Toggle filter cursor through entity types
                    self.status_message = format!("Active filters: {} types", self.type_filters.len());
                }
                _ => {}
            },
            InputMode::BranchNav => match key.code {
                KeyCode::Esc => self.input_mode = InputMode::Normal,
                KeyCode::Char(c @ '0'..='9') => {
                    let idx = (c as u8 - b'0') as usize;
                    if idx < self.layout.timelines.len() {
                        let tl = &self.layout.timelines[idx];
                        self.layout.viewport.time_start = tl.x_start;
                        self.layout.viewport.time_end = tl.x_end;
                        self.layout.viewport.lane_start = tl.lane_start;
                        self.layout.viewport.lane_end = tl.lane_end + 2;
                        self.status_message = format!("Focused: {}", tl.name);
                        self.input_mode = InputMode::Normal;
                    }
                }
                _ => {}
            },
            InputMode::CommandPalette => match key.code {
                KeyCode::Esc => self.input_mode = InputMode::Normal,
                KeyCode::Enter => {
                    self.execute_palette_command();
                    self.input_mode = InputMode::Normal;
                }
                KeyCode::Char(c) => self.palette_query.push(c),
                KeyCode::Backspace => { self.palette_query.pop(); }
                _ => {}
            },
            InputMode::CompareSelect => match key.code {
                KeyCode::Esc => {
                    self.compare_mode = false;
                    self.compare_timeline_idx = None;
                    self.input_mode = InputMode::Normal;
                }
                KeyCode::Char(c @ '0'..='9') => {
                    let idx = (c as u8 - b'0') as usize;
                    if idx < self.layout.timelines.len() {
                        self.compare_timeline_idx = Some(idx);
                        self.compare_mode = true;
                        self.status_message = format!("Comparing with: {}", self.layout.timelines[idx].name);
                        self.input_mode = InputMode::Normal;
                    }
                }
                _ => {}
            },
        }
    }

    /// Handle mouse events (Task 63)
    pub fn handle_mouse(&mut self, mouse: crossterm::event::MouseEvent) {
        use crossterm::event::{MouseEventKind, MouseButton};
        match mouse.kind {
            MouseEventKind::ScrollUp => {
                self.save_view_state();
                self.layout.viewport.zoom(1.1);
            }
            MouseEventKind::ScrollDown => {
                self.save_view_state();
                self.layout.viewport.zoom(0.9);
            }
            MouseEventKind::Down(MouseButton::Left) => {
                // Click to select entity at position
                self.click_select(mouse.column, mouse.row);
            }
            _ => {}
        }
    }

    fn click_select(&mut self, col: u16, row: u16) {
        let vp = &self.layout.viewport;
        let time_range = vp.time_end - vp.time_start;
        if time_range <= 0.0 { return; }
        // Approximate: map col to time, row to lane
        let time = vp.time_start + (col as f64 / 80.0) * time_range;
        let lane = vp.lane_start + row as usize;

        if let Some(ent) = self.layout.entities.iter().find(|e| {
            e.lane == lane && e.x_start <= time && e.x_end >= time
        }) {
            self.selected_entity = Some(ent.entity_id);
            self.status_message = format!("Selected: {}", ent.name);
        }
    }

    /// Advance time cursor when playing (Task 54)
    pub fn tick(&mut self) {
        if self.scrubber_playing {
            self.time_cursor += 0.5;
            if self.time_cursor > self.layout.viewport.time_end {
                self.time_cursor = self.layout.viewport.time_start;
            }
        }
    }

    fn cycle_selection(&mut self) {
        if self.layout.entities.is_empty() { return; }
        let current_idx = self.selected_entity.and_then(|id| {
            self.layout.entities.iter().position(|e| e.entity_id == id)
        });
        let next = match current_idx {
            Some(i) => (i + 1) % self.layout.entities.len(),
            None => 0,
        };
        let ent = &self.layout.entities[next];
        self.selected_entity = Some(ent.entity_id);
        self.status_message = format!("Selected: {}", ent.name);
    }

    fn drill_down(&mut self) {
        // If an entity is selected, focus on it (old select_current behavior)
        // Also push current viewport onto drill stack for back-navigation
        if let Some(id) = self.selected_entity {
            let coords = self.layout.entities.iter()
                .find(|e| e.entity_id == id)
                .map(|ent| (ent.timeline_id, (ent.x_start + ent.x_end) / 2.0, ent.lane));
            if let Some((_tid, cx, lane)) = coords {
                let vp = &self.layout.viewport;
                self.drill_stack.push(ViewState {
                    time_start: vp.time_start, time_end: vp.time_end,
                    lane_start: vp.lane_start, lane_end: vp.lane_end,
                    scale: vp.scale, selected: self.selected_entity,
                });
                // Find the timeline this entity belongs to and zoom to it
                if let Some(tl) = self.layout.timelines.iter().find(|t| {
                    self.layout.entities.iter().any(|e| e.entity_id == id && e.timeline_id == t.timeline_id)
                }) {
                    self.layout.viewport.time_start = tl.x_start;
                    self.layout.viewport.time_end = tl.x_end;
                    self.layout.viewport.lane_start = tl.lane_start;
                    self.layout.viewport.lane_end = tl.lane_end + 2;
                } else {
                    self.layout.viewport.focus(cx, lane);
                }
                self.status_message = "Drilled in".to_string();
            }
        }
    }

    fn drill_up(&mut self) {
        if let Some(state) = self.drill_stack.pop() {
            self.restore_view_state(state);
            self.status_message = "Drilled out".to_string();
        }
    }

    fn select_current(&mut self) {
        if let Some(id) = self.selected_entity {
            let coords = self.layout.entities.iter()
                .find(|e| e.entity_id == id)
                .map(|ent| ((ent.x_start + ent.x_end) / 2.0, ent.lane));
            if let Some((cx, lane)) = coords {
                self.save_view_state();
                self.layout.viewport.focus(cx, lane);
            }
        }
    }

    fn jump_to_search(&mut self) {
        let query = self.search_query.to_lowercase();
        if let Some(ent) = self.layout.entities.iter().find(|e| e.name.to_lowercase().contains(&query)) {
            self.selected_entity = Some(ent.entity_id);
            self.layout.viewport.focus((ent.x_start + ent.x_end) / 2.0, ent.lane);
            self.status_message = format!("Found: {}", ent.name);
        } else {
            self.status_message = format!("Not found: {}", self.search_query);
        }
    }

    /// Check if entity type is visible (Task 55)
    pub fn is_type_visible(&self, entity_type: &str) -> bool {
        self.type_filters.contains(entity_type)
    }

    /// Check if edge label is visible (Task 56)
    pub fn is_edge_visible(&self, label: &str) -> bool {
        if self.active_layer == 0 { return true; }
        self.layer_names.get(self.active_layer).map_or(true, |l| l == label)
    }

    fn execute_palette_command(&mut self) {
        let q = self.palette_query.to_lowercase();
        let matched = self.available_commands.iter()
            .find(|(name, _)| name.contains(&q.as_str()));
        if let Some((cmd, _)) = matched {
            match *cmd {
                "quit" => self.should_quit = true,
                "search" => { self.input_mode = InputMode::Search; self.search_query.clear(); }
                "filter" => self.input_mode = InputMode::Filter,
                "help" => self.input_mode = InputMode::Help,
                "branches" => self.input_mode = InputMode::BranchNav,
                "zoom-in" => { self.save_view_state(); self.layout.viewport.zoom(1.2); }
                "zoom-out" => { self.save_view_state(); self.layout.viewport.zoom(0.8); }
                "reset" => {
                    self.layout.viewport.scale = 1.0;
                    self.status_message = "Reset".to_string();
                }
                "play" => {
                    self.scrubber_playing = !self.scrubber_playing;
                    self.status_message = if self.scrubber_playing { "▶".into() } else { "⏸".into() };
                }
                "next-entity" => self.cycle_selection(),
                "bookmark" => {
                    let idx = (self.bookmarks.len() as u8) + 1;
                    if idx <= 9 {
                        let vp = &self.layout.viewport;
                        self.bookmarks.insert(idx, ViewState {
                            time_start: vp.time_start, time_end: vp.time_end,
                            lane_start: vp.lane_start, lane_end: vp.lane_end,
                            scale: vp.scale, selected: self.selected_entity,
                        });
                        self.status_message = format!("Bookmark {} saved", idx);
                    }
                }
                "undo" => {
                    if let Some(state) = self.undo_stack.pop() {
                        let cur = ViewState {
                            time_start: self.layout.viewport.time_start,
                            time_end: self.layout.viewport.time_end,
                            lane_start: self.layout.viewport.lane_start,
                            lane_end: self.layout.viewport.lane_end,
                            scale: self.layout.viewport.scale,
                            selected: self.selected_entity,
                        };
                        self.redo_stack.push(cur);
                        self.restore_view_state(state);
                    }
                }
                "redo" => {
                    if let Some(state) = self.redo_stack.pop() {
                        let cur = ViewState {
                            time_start: self.layout.viewport.time_start,
                            time_end: self.layout.viewport.time_end,
                            lane_start: self.layout.viewport.lane_start,
                            lane_end: self.layout.viewport.lane_end,
                            scale: self.layout.viewport.scale,
                            selected: self.selected_entity,
                        };
                        self.undo_stack.push(cur);
                        self.restore_view_state(state);
                    }
                }
                _ => {}
            }
        } else {
            self.status_message = format!("Unknown command: {}", self.palette_query);
        }
    }
}
