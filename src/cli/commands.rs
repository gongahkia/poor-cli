use clap::{Parser, Subcommand};
use std::path::PathBuf;

/// Seuss: a DSL for modeling and visualizing temporal narratives
#[derive(Parser)]
#[command(name = "seuss", version, about)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,

    /// Enable verbose output
    #[arg(long, global = true)]
    pub verbose: bool,

    /// Config file path
    #[arg(long, global = true)]
    pub config: Option<PathBuf>,

    /// Theme name
    #[arg(long, global = true)]
    pub theme: Option<String>,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Parse and visualize a .seuss file in the terminal
    Run {
        /// Path to .seuss source file
        file: PathBuf,
    },
    /// Export timeline as SVG/PDF/PNG
    Export {
        /// Path to .seuss source file
        file: PathBuf,
        /// Output format
        #[arg(short, long, default_value = "svg")]
        format: String,
        /// Output file path
        #[arg(short, long)]
        output: Option<PathBuf>,
        /// Width in pixels
        #[arg(long)]
        width: Option<u32>,
        /// Height in pixels
        #[arg(long)]
        height: Option<u32>,
        /// Time range (start..end)
        #[arg(long)]
        time_range: Option<String>,
        /// DPI for PNG export
        #[arg(long, default_value = "150")]
        dpi: u32,
    },
    /// Import from external formats
    Import {
        /// Input file path
        file: PathBuf,
        /// Source format (csv, gedcom, jsonld)
        #[arg(long, default_value = "csv")]
        from: String,
        /// Output .seuss file path
        #[arg(short, long)]
        output: Option<PathBuf>,
    },
    /// Validate a .seuss file without rendering
    Check {
        /// Path to .seuss source file
        file: PathBuf,
    },
    /// Interactive REPL mode
    Repl,
    /// Diff two .seuss files
    Diff {
        /// First .seuss file
        file1: PathBuf,
        /// Second .seuss file
        file2: PathBuf,
    },
}
