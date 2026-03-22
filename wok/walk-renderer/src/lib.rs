//! Walk renderer: GPU rendering, glyph atlas, and text layout.
#![deny(missing_docs)]
#![allow(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]
#![allow(clippy::similar_names)]

pub mod atlas;
pub mod compositor;
pub mod damage;
pub mod font;
pub mod gpu;
pub mod pipeline;
pub mod text_layout;
