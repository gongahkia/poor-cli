//! Walk app: entry point, event loop, window management, and application shell.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]
#![allow(clippy::too_many_lines)]
#![allow(clippy::must_use_candidate)]
#![allow(clippy::missing_panics_doc)]
#![allow(clippy::missing_errors_doc)]
#![allow(clippy::doc_markdown)]
#![allow(clippy::missing_const_for_fn)]
#![allow(clippy::trivially_copy_pass_by_ref)]
#![allow(clippy::struct_excessive_bools)]
#![allow(clippy::cast_possible_wrap)]
#![allow(clippy::option_if_let_else)]
#![allow(clippy::match_same_arms)]
#![allow(clippy::map_unwrap_or)]
#![allow(clippy::redundant_clone)]
#![allow(clippy::implicit_clone)]
#![allow(clippy::significant_drop_tightening)]
#![allow(clippy::manual_flatten)]
#![allow(clippy::float_cmp)]
#![allow(clippy::use_self)]
#![allow(clippy::cast_lossless)]

pub mod action_effects;
pub mod app;
pub mod block_query;
pub mod command_search;
pub mod config;
pub mod dpi;
pub mod event_loop;
pub mod frame_clock;
pub mod handler;
pub mod input;
pub mod keybindings;
pub mod plugin_host;
pub mod scripting;
pub mod session;
pub mod window;
pub mod workspace;
