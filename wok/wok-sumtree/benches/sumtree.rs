//! Benchmarks comparing `SumTree<Line>` against `Vec<Line>` for the operations
//! that matter to scrollback: bulk push, random `get`, and `seek_by` row jumps.

use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use wok_sumtree::{Item, SumTree, Summary};

#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct LineCount(usize);
impl Summary for LineCount {
    fn add(&mut self, other: &Self) {
        self.0 += other.0;
    }
}

#[derive(Debug, Clone)]
struct Line(String);
impl Item for Line {
    type Summary = LineCount;
    fn summary(&self) -> LineCount {
        LineCount(1)
    }
}

fn make_lines(n: usize) -> Vec<Line> {
    (0..n).map(|i| Line(format!("line-{i}"))).collect()
}

fn bench_push(c: &mut Criterion) {
    let mut group = c.benchmark_group("push");
    for &n in &[1_000usize, 10_000, 100_000] {
        let lines = make_lines(n);
        group.bench_with_input(BenchmarkId::new("vec", n), &lines, |b, lines| {
            b.iter(|| {
                let mut v: Vec<Line> = Vec::new();
                for l in lines {
                    v.push(l.clone());
                }
                black_box(v.len())
            });
        });
        group.bench_with_input(BenchmarkId::new("sumtree", n), &lines, |b, lines| {
            b.iter(|| {
                let mut t: SumTree<Line> = SumTree::new();
                for l in lines {
                    t.push(l.clone());
                }
                black_box(t.len())
            });
        });
    }
    group.finish();
}

fn bench_get(c: &mut Criterion) {
    let mut group = c.benchmark_group("get_random");
    for &n in &[1_000usize, 10_000, 100_000] {
        let lines = make_lines(n);
        let v: Vec<Line> = lines.clone();
        let mut t: SumTree<Line> = SumTree::new();
        for l in &lines {
            t.push(l.clone());
        }
        let indices: Vec<usize> = (0..1024).map(|i| (i * 31) % n).collect();
        group.bench_with_input(
            BenchmarkId::new("vec", n),
            &(&v, &indices),
            |b, (v, idx)| {
                b.iter(|| {
                    let mut sum = 0;
                    for &i in idx.iter() {
                        sum += v[i].0.len();
                    }
                    black_box(sum)
                });
            },
        );
        group.bench_with_input(
            BenchmarkId::new("sumtree", n),
            &(&t, &indices),
            |b, (t, idx)| {
                b.iter(|| {
                    let mut sum = 0;
                    for &i in idx.iter() {
                        sum += t.get(i).unwrap().0.len();
                    }
                    black_box(sum)
                });
            },
        );
    }
    group.finish();
}

fn bench_seek(c: &mut Criterion) {
    let mut group = c.benchmark_group("seek_row");
    for &n in &[1_000usize, 10_000, 100_000] {
        let lines = make_lines(n);
        let mut t: SumTree<Line> = SumTree::new();
        for l in &lines {
            t.push(l.clone());
        }
        let targets: Vec<usize> = (0..1024).map(|i| ((i * 47) % n) + 1).collect();
        // Vec equivalent: linear scan that counts items until we hit `target`.
        let v = lines.clone();
        group.bench_with_input(
            BenchmarkId::new("vec_linear", n),
            &(&v, &targets),
            |b, (v, ts)| {
                b.iter(|| {
                    let mut hit = 0usize;
                    for &t in ts.iter() {
                        let mut acc = 0;
                        for (i, _) in v.iter().enumerate() {
                            acc += 1;
                            if acc >= t {
                                hit ^= i;
                                break;
                            }
                        }
                    }
                    black_box(hit)
                });
            },
        );
        group.bench_with_input(
            BenchmarkId::new("sumtree", n),
            &(&t, &targets),
            |b, (t, ts)| {
                b.iter(|| {
                    let mut hit = 0usize;
                    for &target in ts.iter() {
                        if let Some(i) = t.seek_by(target, &|s: &LineCount| s.0) {
                            hit ^= i;
                        }
                    }
                    black_box(hit)
                });
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_push, bench_get, bench_seek);
criterion_main!(benches);
