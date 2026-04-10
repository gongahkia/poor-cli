use std::io;
use std::sync::mpsc;
use std::time::Duration;

use crossterm::event;
use ratatui::{backend::CrosstermBackend, Terminal};

use crate::app::App;
use crate::input::{self, InputAction};
use crate::ui;

pub enum LoopControl {
    Continue,
    Break,
}

pub fn run_event_loop<M, FTick, FServerMsg, FInput>(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
    rx: &mpsc::Receiver<M>,
    mut on_tick: FTick,
    mut on_server_message: FServerMsg,
    mut on_input_action: FInput,
) -> Result<(), Box<dyn std::error::Error>>
where
    FTick: FnMut(&mut App) -> Result<LoopControl, Box<dyn std::error::Error>>,
    FServerMsg: FnMut(&mut App, M) -> Result<LoopControl, Box<dyn std::error::Error>>,
    FInput: FnMut(&mut App, InputAction) -> Result<LoopControl, Box<dyn std::error::Error>>,
{
    loop {
        terminal.draw(|f| ui::draw(f, app))?;

        while let Ok(msg) = rx.try_recv() {
            match on_server_message(app, msg)? {
                LoopControl::Continue => {}
                LoopControl::Break => return Ok(()),
            }
        }

        match on_tick(app)? {
            LoopControl::Continue => {}
            LoopControl::Break => return Ok(()),
        }

        app.clear_old_status();
        app.tick_spinner();

        if event::poll(Duration::from_millis(100))? {
            let ev = event::read()?;
            let input_action = input::handle_event(app, ev);
            match on_input_action(app, input_action)? {
                LoopControl::Continue => {}
                LoopControl::Break => return Ok(()),
            }
        }
    }
}
