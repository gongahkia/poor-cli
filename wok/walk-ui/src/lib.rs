//! Walk UI: layout, tabs, splits, viewport, theme, clipboard, selection, and search.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]
#![allow(clippy::must_use_candidate)]
#![allow(clippy::missing_panics_doc)]
#![allow(clippy::missing_errors_doc)]
#![allow(clippy::doc_markdown)]
#![allow(clippy::missing_const_for_fn)]
#![allow(clippy::trivially_copy_pass_by_ref)]
#![allow(clippy::struct_excessive_bools)]
#![allow(clippy::cast_possible_wrap)]
#![allow(clippy::many_single_char_names)]
#![allow(clippy::match_same_arms)]
#![allow(clippy::map_unwrap_or)]
#![allow(clippy::option_if_let_else)]
#![allow(clippy::use_self)]
#![allow(clippy::match_wildcard_for_single_variants)]

pub mod background;
pub mod bell;
pub mod clipboard;
pub mod layout;
pub mod links;
pub mod quick_select;
pub mod search;
pub mod selection;
pub mod splits;
pub mod status_bar;
pub mod tab_bar;
pub mod tabs;
pub mod theme;
pub mod theme_loader;
pub mod theme_watcher;
pub mod viewport;
pub mod zoom;
