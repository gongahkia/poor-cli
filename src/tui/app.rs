use crate::layout::engine::{Layout, Viewport};
use crate::model::types::Id;

/// Input mode
#[derive(Debug, Clone, PartialEq)]
pub enum InputMode {
    Normal,
    Search,
    Filter,
    Help,
}

/// App state (Task 48)
pub struct App {
    pub layout: Layout,
    pub input_mode: InputMode,
    pub selected_entity: Option<Id>,
    pub should_quit: bool,
    pub search_query: String,
    pub status_message: String,
}

impl App {
    pub fn new(layout: Layout) -> Self {
        Self {
            layout,
            input_mode: InputMode::Normal,
            selected_entity: None,
            should_quit: false,
            search_query: String::new(),
            status_message: String::new(),
        }
    }

    /// Keyboard navigation (Task 52)
    pub fn handle_key(&mut self, key: crossterm::event::KeyEvent) {
        use crossterm::event::KeyCode;
        match self.input_mode {
            InputMode::Normal => match key.code {
                KeyCode::Char('q') => self.should_quit = true,
                KeyCode::Char('h') | KeyCode::Left => self.layout.viewport.pan(-5.0, 0),
                KeyCode::Char('l') | KeyCode::Right => self.layout.viewport.pan(5.0, 0),
                KeyCode::Char('k') | KeyCode::Up => self.layout.viewport.pan(0.0, -1),
                KeyCode::Char('j') | KeyCode::Down => self.layout.viewport.pan(0.0, 1),
                KeyCode::Char('+') | KeyCode::Char('=') => self.layout.viewport.zoom(1.2),
                KeyCode::Char('-') => self.layout.viewport.zoom(0.8),
                KeyCode::Tab => self.cycle_selection(),
                KeyCode::Enter => self.select_current(),
                KeyCode::Esc => {
                    self.selected_entity = None;
                    self.status_message = "Deselected".to_string();
                }
                KeyCode::Char('?') => self.input_mode = InputMode::Help,
                KeyCode::Char('/') => {
                    self.input_mode = InputMode::Search;
                    self.search_query.clear();
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
                _ => {}
            },
        }
    }

    /// Entity selection (Task 53)
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

    fn select_current(&mut self) {
        if let Some(id) = self.selected_entity {
            if let Some(ent) = self.layout.entities.iter().find(|e| e.entity_id == id) {
                self.layout.viewport.focus(
                    (ent.x_start + ent.x_end) / 2.0,
                    ent.lane,
                );
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
}
