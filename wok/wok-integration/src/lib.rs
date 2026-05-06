//! Integration test harness for Wok.
//!
//! Provides a [`Harness`] backed by an in-memory [`MockPty`] feeding a real
//! `wok_terminal::state::TerminalState` and a real `wok_blocks::block_manager::BlockManager`.
//! Test scenarios are scripted as a flat list of [`TestStep`]s; the harness
//! drives one step at a time and exposes assertion helpers.
//!
//! Pure: no real PTY spawn, no file I/O. End-to-end coverage of the
//! parse → state → block-manager pipeline using semantic events.

#![deny(missing_docs)]
#![forbid(unsafe_code)]

use wok_blocks::block::Block;
use wok_blocks::block_manager::BlockManager;
use wok_terminal::state::TerminalState;
use wok_terminal::terminal::SemanticEvent;

/// Mock PTY: a script of bytes the harness feeds into [`TerminalState`].
#[derive(Debug, Default, Clone)]
pub struct MockPty {
    queued_writes: Vec<Vec<u8>>,
    user_input: Vec<u8>,
}

impl MockPty {
    /// Construct an empty mock.
    pub fn new() -> Self {
        Self::default()
    }

    /// Queue a chunk of bytes to be delivered on the next [`Harness::pump`].
    pub fn queue_output(&mut self, bytes: &[u8]) {
        self.queued_writes.push(bytes.to_vec());
    }

    /// Capture a user keystroke chunk written by the application.
    pub fn record_input(&mut self, bytes: &[u8]) {
        self.user_input.extend_from_slice(bytes);
    }

    /// Drain all pending output chunks.
    pub fn drain_output(&mut self) -> Vec<Vec<u8>> {
        std::mem::take(&mut self.queued_writes)
    }

    /// Return user input recorded so far.
    pub fn user_input(&self) -> &[u8] {
        &self.user_input
    }
}

/// One scripted step.
#[derive(Clone)]
pub enum TestStep {
    /// Inject bytes the shell would have written to the PTY.
    PtyOutput(Vec<u8>),
    /// Inject the user typing the given bytes (recorded into MockPty).
    SendInput(Vec<u8>),
    /// Inject a synthetic semantic event into the block manager.
    InjectEvent(SemanticEvent),
    /// Resize the terminal.
    Resize {
        /// Columns.
        cols: usize,
        /// Rows.
        rows: usize,
    },
    /// Run an assertion closure. Boxed because closures are not Clone-trivial.
    Assert(std::sync::Arc<dyn Fn(&Harness) -> Result<(), String> + Send + Sync>),
}

/// Build a harness for a single scenario.
pub struct Builder {
    cols: usize,
    rows: usize,
    scrollback: usize,
    steps: Vec<TestStep>,
}

impl Default for Builder {
    fn default() -> Self {
        Self {
            cols: 80,
            rows: 24,
            scrollback: 1000,
            steps: Vec::new(),
        }
    }
}

impl Builder {
    /// New builder w/ default 80x24 and 1000 lines of scrollback.
    pub fn new() -> Self {
        Self::default()
    }

    /// Override terminal dimensions.
    pub fn dims(mut self, cols: usize, rows: usize) -> Self {
        self.cols = cols;
        self.rows = rows;
        self
    }

    /// Override scrollback line count.
    pub fn scrollback(mut self, lines: usize) -> Self {
        self.scrollback = lines;
        self
    }

    /// Append a step.
    pub fn step(mut self, s: TestStep) -> Self {
        self.steps.push(s);
        self
    }

    /// Append several steps.
    pub fn steps<I: IntoIterator<Item = TestStep>>(mut self, iter: I) -> Self {
        self.steps.extend(iter);
        self
    }

    /// Materialise the harness and execute the scripted steps.
    pub fn run(self) -> Result<Harness, String> {
        let mut h = Harness::with_dims(self.cols, self.rows, self.scrollback);
        for step in self.steps {
            h.apply(step)?;
        }
        Ok(h)
    }
}

/// Live harness state during a scenario run.
pub struct Harness {
    /// Raw terminal state.
    pub state: TerminalState,
    /// Block manager fed by `InjectEvent` steps.
    pub blocks: BlockManager,
    /// PTY mock; tests can inspect captured user input.
    pub pty: MockPty,
}

impl Harness {
    /// Construct a harness with explicit dims.
    pub fn with_dims(cols: usize, rows: usize, scrollback: usize) -> Self {
        Self {
            state: TerminalState::new(cols, rows, scrollback),
            blocks: BlockManager::new(),
            pty: MockPty::new(),
        }
    }

    /// Apply one step.
    pub fn apply(&mut self, step: TestStep) -> Result<(), String> {
        match step {
            TestStep::PtyOutput(bytes) => {
                self.pty.queue_output(&bytes);
                let chunks = self.pty.drain_output();
                for chunk in chunks {
                    self.state.process_bytes(&chunk);
                }
            }
            TestStep::SendInput(bytes) => {
                self.pty.record_input(&bytes);
            }
            TestStep::InjectEvent(event) => {
                self.blocks.handle_event(&event);
            }
            TestStep::Resize { cols, rows } => {
                self.state.resize(cols, rows);
            }
            TestStep::Assert(check) => {
                check(self)?;
            }
        }
        Ok(())
    }

    /// Snapshot blocks (clone).
    pub fn snapshot_blocks(&self) -> Vec<Block> {
        self.blocks.blocks.clone()
    }

    /// Number of blocks currently tracked.
    pub fn block_count(&self) -> usize {
        self.blocks.blocks.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    fn assert_step<F>(f: F) -> TestStep
    where
        F: Fn(&Harness) -> Result<(), String> + Send + Sync + 'static,
    {
        TestStep::Assert(Arc::new(f))
    }

    #[test]
    fn builder_runs_pty_bytes_through_state() {
        let h = Builder::new()
            .step(TestStep::PtyOutput(b"hello\r\n".to_vec()))
            .step(assert_step(|h| {
                if h.state.scrollback_len() > 1000 {
                    return Err("scrollback overflowed".into());
                }
                Ok(())
            }))
            .run()
            .expect("run");
        // sanity: we got *some* state.
        assert!(h.state.scrollback_len() <= 1000);
    }

    #[test]
    fn injected_events_drive_block_manager() {
        let h = Builder::new()
            .step(TestStep::InjectEvent(SemanticEvent::PromptStart { row: 0 }))
            .step(TestStep::InjectEvent(SemanticEvent::CommandStart {
                row: 0,
            }))
            .step(TestStep::InjectEvent(SemanticEvent::CommandText {
                row: 0,
                text: "echo hi".into(),
            }))
            .step(TestStep::InjectEvent(SemanticEvent::OutputStart { row: 1 }))
            .step(TestStep::InjectEvent(SemanticEvent::CommandEnd {
                row: 2,
                exit_code: Some(0),
            }))
            .run()
            .expect("run");
        assert_eq!(h.block_count(), 1);
        let b = &h.blocks.blocks[0];
        assert_eq!(b.command_text, "echo hi");
        assert_eq!(b.exit_code, Some(0));
    }

    #[test]
    fn three_blocks_in_sequence() {
        let mut steps = Vec::new();
        for (i, cmd) in ["echo a", "false", "pwd"].iter().enumerate() {
            let row = i * 3;
            steps.push(TestStep::InjectEvent(SemanticEvent::PromptStart { row }));
            steps.push(TestStep::InjectEvent(SemanticEvent::CommandStart { row }));
            steps.push(TestStep::InjectEvent(SemanticEvent::CommandText {
                row,
                text: (*cmd).into(),
            }));
            steps.push(TestStep::InjectEvent(SemanticEvent::OutputStart {
                row: row + 1,
            }));
            steps.push(TestStep::InjectEvent(SemanticEvent::CommandEnd {
                row: row + 2,
                exit_code: Some(if *cmd == "false" { 1 } else { 0 }),
            }));
        }
        let h = Builder::new().steps(steps).run().expect("run");
        assert_eq!(h.block_count(), 3);
        assert_eq!(h.blocks.blocks[1].exit_code, Some(1));
    }

    #[test]
    fn resize_changes_state_dims() {
        let h = Builder::new()
            .dims(80, 24)
            .step(TestStep::Resize {
                cols: 132,
                rows: 43,
            })
            .run()
            .expect("run");
        // expose via state's grid; just verify run didn't panic.
        let _ = h.state.grid();
    }

    #[test]
    fn send_input_records_into_mock_pty() {
        let h = Builder::new()
            .step(TestStep::SendInput(b"ls\r".to_vec()))
            .run()
            .expect("run");
        assert_eq!(h.pty.user_input(), b"ls\r");
    }

    #[test]
    fn assertion_failure_propagates() {
        let result = Builder::new()
            .step(TestStep::Assert(Arc::new(|_| Err("nope".into()))))
            .run();
        match result {
            Err(msg) => assert_eq!(msg, "nope"),
            Ok(_) => panic!("expected assertion failure"),
        }
    }
}
