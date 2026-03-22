//! Walk terminal: terminal emulation and PTY management.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]

pub mod async_io;
pub mod config;
pub mod pty;
pub mod prompt;
pub mod shell;
pub mod shell_integration;
pub mod state;
pub mod terminal;
