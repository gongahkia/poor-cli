//! Wok renderer: GPU rendering, glyph atlas, and text layout.
#![deny(missing_docs)]
#![allow(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]
#![allow(clippy::similar_names)]
#![allow(clippy::must_use_candidate)]
#![allow(clippy::missing_panics_doc)]
#![allow(clippy::missing_errors_doc)]
#![allow(clippy::doc_markdown)]
#![allow(clippy::missing_const_for_fn)]
#![allow(clippy::trivially_copy_pass_by_ref)]
#![allow(clippy::struct_excessive_bools)]
#![allow(clippy::cast_possible_wrap)]
#![allow(clippy::too_many_lines)]
#![allow(clippy::default_trait_access)]
#![allow(clippy::suboptimal_flops)]
#![allow(clippy::explicit_iter_loop)]

pub mod atlas;
pub mod damage;
pub mod font;
pub mod gpu;
pub mod inline_images;
pub mod pipeline;
pub mod render_pipeline;
pub mod text_layout;
