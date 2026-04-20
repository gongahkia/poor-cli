use criterion::{black_box, criterion_group, criterion_main, BatchSize, Criterion, Throughput};
use wok_app::block_query::{BlockQueryMode, BlockQueryState};
use wok_app::command_search::CommandSearchState;
use wok_input::history::HistoryEntry;
use wok_ui::search::{GlobalSearch, SearchLine};

const GLOBAL_SEARCH_LINES: usize = 50_000;
const BLOCK_QUERY_LINES: usize = 20_000;
const PANE_HISTORY_ENTRIES: usize = 4_000;
const GLOBAL_HISTORY_ENTRIES: usize = 40_000;

fn bench_global_search(c: &mut Criterion) {
    let lines = make_search_lines(GLOBAL_SEARCH_LINES, 16);
    let mut group = c.benchmark_group("large_workspace/global_search");
    group.throughput(Throughput::Elements(lines.len() as u64));
    group.bench_function("query_error", |b| {
        b.iter_batched(
            GlobalSearch::new,
            |mut search| {
                search.search("error", &lines);
                black_box(search.matches.len());
            },
            BatchSize::SmallInput,
        );
    });
    group.finish();
}

fn bench_block_query_filter(c: &mut Criterion) {
    let lines = make_output_lines(BLOCK_QUERY_LINES, 11);
    let mut group = c.benchmark_group("large_workspace/block_query");
    group.throughput(Throughput::Elements(lines.len() as u64));
    group.bench_function("filter_timeout", |b| {
        b.iter_batched(
            || BlockQueryState::new(BlockQueryMode::Filter, 42),
            |mut state| {
                state.search("timeout", &lines);
                black_box(state.matches.len());
                black_box(state.filtered_line_indices().len());
            },
            BatchSize::SmallInput,
        );
    });
    group.finish();
}

fn bench_command_search(c: &mut Criterion) {
    let pane_entries = make_history_entries(PANE_HISTORY_ENTRIES, Some(11), 5);
    let global_entries = make_history_entries(GLOBAL_HISTORY_ENTRIES, None, 7);
    let total_entries = pane_entries.len() + global_entries.len();
    let mut group = c.benchmark_group("large_workspace/command_search");
    group.throughput(Throughput::Elements(total_entries as u64));
    group.bench_function("query_cargo_test", |b| {
        b.iter_batched(
            CommandSearchState::new,
            |mut state| {
                state.search("cargo test", &pane_entries, &global_entries);
                black_box(state.results.len());
            },
            BatchSize::SmallInput,
        );
    });
    group.finish();
}

fn make_search_lines(total: usize, match_every: usize) -> Vec<SearchLine> {
    (0..total)
        .map(|row| SearchLine {
            pane_id: (row % 6) as u64 + 1,
            tab_id: (row % 3) as u64 + 1,
            row,
            block_id: if row % 13 == 0 {
                Some((row % 97) as u64 + 1)
            } else {
                None
            },
            is_command: row % 9 == 0,
            text: if row % match_every == 0 {
                format!("worker-{row:05} timeout error while running cargo test")
            } else {
                format!("worker-{row:05} completed successfully with no output")
            },
        })
        .collect()
}

fn make_output_lines(total: usize, match_every: usize) -> Vec<String> {
    (0..total)
        .map(|idx| {
            if idx % match_every == 0 {
                format!("request-{idx:05} timeout while waiting for service response")
            } else {
                format!("request-{idx:05} completed")
            }
        })
        .collect()
}

fn make_history_entries(
    total: usize,
    source_pane_id: Option<u64>,
    match_every: usize,
) -> Vec<HistoryEntry> {
    (0..total)
        .map(|idx| HistoryEntry {
            command: if idx % match_every == 0 {
                format!("cargo test --package crate_{idx:05}")
            } else {
                format!("git status --short --untracked-files={idx}")
            },
            cwd: None,
            source_pane_id,
            started_at_ms: idx as u64,
            completed_at_ms: Some(idx as u64 + 1),
            exit_code: Some(0),
            duration_ms: Some((idx % 1500) as u64 + 1),
        })
        .collect()
}

criterion_group!(
    benches,
    bench_global_search,
    bench_block_query_filter,
    bench_command_search
);
criterion_main!(benches);
