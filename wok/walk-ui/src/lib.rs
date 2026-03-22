//! Walk UI: layout, tabs, splits, viewport, theme, clipboard, selection, and search.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]

pub mod background;
pub mod bell;
pub mod clipboard;
pub mod layout;
pub mod links;
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
