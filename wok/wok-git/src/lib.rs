//! Git parsing primitives for Wok.
//!
//! This crate intentionally keeps parsing independent from process execution
//! and UI state. Callers can feed output from `git status --porcelain=v1 -z`,
//! `git diff --numstat`, or unified diff patches and reuse the typed results
//! across block metadata, VCS panels, RPC, and tests.

#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::must_use_candidate)]
#![allow(clippy::missing_panics_doc)]
#![allow(clippy::missing_errors_doc)]

pub mod diff;
pub mod repo;
pub mod service;
pub mod status;
