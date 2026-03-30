//! Walk input: gap buffer editor, cursor ops, syntax highlighting, and history.
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
#![allow(clippy::needless_pass_by_value)]
#![allow(clippy::too_many_lines)]
#![allow(clippy::should_implement_trait)]
#![allow(clippy::option_if_let_else)]
#![allow(clippy::map_unwrap_or)]
#![allow(clippy::assign_op_pattern)]
#![allow(clippy::branches_sharing_code)]
#![allow(clippy::collapsible_if)]
#![allow(clippy::incompatible_msrv)]

pub mod brackets;
pub mod buffer;
pub mod completion;
pub mod cursor_ops;
pub mod editor;
pub mod highlighter;
pub mod history;
pub mod workflows;
