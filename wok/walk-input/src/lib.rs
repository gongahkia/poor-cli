//! Walk input: gap buffer editor, cursor ops, syntax highlighting, and history.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]

pub mod brackets;
pub mod buffer;
pub mod cursor_ops;
pub mod editor;
pub mod highlighter;
pub mod history;
