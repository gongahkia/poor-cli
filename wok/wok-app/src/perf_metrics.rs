use std::time::{Duration, Instant};

use sysinfo::{get_current_pid, Disks, Pid, ProcessRefreshKind, ProcessesToUpdate, System};
use tracing::warn;

#[derive(Clone, Debug, Default)]
pub(crate) struct BatterySnapshot {
    pub(crate) percent: Option<f32>,
    pub(crate) state: Option<String>,
    pub(crate) time_remaining: Option<String>,
}

#[derive(Clone, Debug, Default)]
pub(crate) struct SystemMetricsSnapshot {
    pub(crate) cpu_usage_percent: f32,
    pub(crate) memory_used_bytes: u64,
    pub(crate) memory_total_bytes: u64,
    pub(crate) app_cpu_usage_percent: Option<f32>,
    pub(crate) app_memory_bytes: Option<u64>,
    pub(crate) disk_total_bytes: u64,
    pub(crate) disk_available_bytes: u64,
    pub(crate) app_disk_read_bytes: Option<u64>,
    pub(crate) app_disk_written_bytes: Option<u64>,
    pub(crate) battery: Option<BatterySnapshot>,
    pub(crate) warnings: Vec<String>,
}

pub(crate) struct SystemMetricsSampler {
    system: System,
    disks: Disks,
    current_pid: Option<Pid>,
    interval: Duration,
    last_sample: Option<Instant>,
    battery_last_sample: Option<Instant>,
    snapshot: SystemMetricsSnapshot,
    logged_pid_warning: bool,
    logged_battery_warning: bool,
}

impl SystemMetricsSampler {
    pub(crate) fn new(interval: Duration) -> Self {
        let mut system = System::new();
        system.refresh_memory();
        system.refresh_cpu_all();
        let disks = Disks::new_with_refreshed_list();
        let current_pid = match get_current_pid() {
            Ok(pid) => Some(pid),
            Err(error) => {
                warn!("failed to determine current process id for app metrics: {error}");
                None
            }
        };
        let mut sampler = Self {
            system,
            disks,
            current_pid,
            interval,
            last_sample: None,
            battery_last_sample: None,
            snapshot: SystemMetricsSnapshot::default(),
            logged_pid_warning: false,
            logged_battery_warning: false,
        };
        sampler.refresh_now();
        sampler
    }

    pub(crate) fn maybe_refresh(&mut self) -> bool {
        if self
            .last_sample
            .is_some_and(|last_sample| last_sample.elapsed() < self.interval)
        {
            return false;
        }
        self.refresh_now();
        true
    }

    pub(crate) fn snapshot(&self) -> &SystemMetricsSnapshot {
        &self.snapshot
    }

    fn refresh_now(&mut self) {
        self.system.refresh_cpu_usage();
        self.system.refresh_memory();
        if let Some(pid) = self.current_pid {
            let process_kind = ProcessRefreshKind::nothing()
                .with_cpu()
                .with_memory()
                .with_disk_usage();
            self.system.refresh_processes_specifics(
                ProcessesToUpdate::Some(&[pid]),
                true,
                process_kind,
            );
        }
        self.disks.refresh(true);

        let (disk_total_bytes, disk_available_bytes) =
            self.disks
                .list()
                .iter()
                .fold((0_u64, 0_u64), |(total_acc, available_acc), disk| {
                    (
                        total_acc.saturating_add(disk.total_space()),
                        available_acc.saturating_add(disk.available_space()),
                    )
                });

        let process = self.current_pid.and_then(|pid| self.system.process(pid));
        let process_available = process.is_some();
        let app_cpu_usage_percent = process.map(sysinfo::Process::cpu_usage);
        let app_memory_bytes = process.map(sysinfo::Process::memory);
        let disk_usage = process.map(sysinfo::Process::disk_usage);
        let battery = self.refresh_battery_if_needed();
        let mut warnings = Vec::new();
        if !process_available && self.current_pid.is_some() {
            warnings.push("app process metrics unavailable".to_string());
            if !self.logged_pid_warning {
                warn!("app process metrics unavailable from sysinfo");
                self.logged_pid_warning = true;
            }
        }
        if battery.is_none() {
            warnings.push("battery unavailable".to_string());
        }

        self.snapshot = SystemMetricsSnapshot {
            cpu_usage_percent: self.system.global_cpu_usage(),
            memory_used_bytes: self.system.used_memory(),
            memory_total_bytes: self.system.total_memory(),
            app_cpu_usage_percent,
            app_memory_bytes,
            disk_total_bytes,
            disk_available_bytes,
            app_disk_read_bytes: disk_usage.map(|usage| usage.read_bytes),
            app_disk_written_bytes: disk_usage.map(|usage| usage.written_bytes),
            battery,
            warnings,
        };
        self.last_sample = Some(Instant::now());
    }

    fn refresh_battery_if_needed(&mut self) -> Option<BatterySnapshot> {
        if self
            .battery_last_sample
            .is_some_and(|last_sample| last_sample.elapsed() < Duration::from_secs(10))
        {
            return self.snapshot.battery.clone();
        }
        self.battery_last_sample = Some(Instant::now());
        match platform_battery_snapshot() {
            Ok(snapshot) => snapshot,
            Err(error) => {
                if !self.logged_battery_warning {
                    warn!("battery metrics unavailable: {error}");
                    self.logged_battery_warning = true;
                }
                None
            }
        }
    }
}

#[cfg(target_os = "macos")]
fn platform_battery_snapshot() -> Result<Option<BatterySnapshot>, String> {
    let output = std::process::Command::new("pmset")
        .args(["-g", "batt"])
        .output()
        .map_err(|error| format!("failed to execute pmset: {error}"))?;
    if !output.status.success() {
        return Err(format!("pmset exited with status {}", output.status));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    Ok(parse_pmset_battery(&stdout))
}

#[cfg(not(target_os = "macos"))]
fn platform_battery_snapshot() -> Result<Option<BatterySnapshot>, String> {
    Err("battery metrics are only implemented for macOS in Wok currently".to_string())
}

#[cfg(target_os = "macos")]
fn parse_pmset_battery(output: &str) -> Option<BatterySnapshot> {
    let line = output.lines().find(|line| line.contains('%'))?;
    let percent = line
        .split(';')
        .next()
        .and_then(|prefix| {
            prefix
                .rsplit_once('\t')
                .map(|(_, suffix)| suffix)
                .or(Some(prefix))
        })
        .and_then(|segment| segment.trim().trim_end_matches('%').parse::<f32>().ok());
    let mut parts = line.split(';').map(str::trim).skip(1);
    let state = parts
        .next()
        .map(ToString::to_string)
        .filter(|s| !s.is_empty());
    let time_remaining = parts.next().and_then(|part| {
        let trimmed = part.trim();
        (!trimmed.is_empty() && trimmed != "no estimate").then(|| trimmed.to_string())
    });
    Some(BatterySnapshot {
        percent,
        state,
        time_remaining,
    })
}

pub(crate) fn format_bytes(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KiB", "MiB", "GiB", "TiB"];
    let mut value = bytes as f64;
    let mut unit = UNITS[0];
    for candidate in UNITS.iter().skip(1) {
        if value < 1024.0 {
            break;
        }
        value /= 1024.0;
        unit = candidate;
    }
    if unit == "B" {
        format!("{bytes} {unit}")
    } else {
        format!("{value:.1} {unit}")
    }
}

pub(crate) fn percent(used: u64, total: u64) -> f32 {
    if total == 0 {
        0.0
    } else {
        used as f32 / total as f32 * 100.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_bytes_uses_binary_units() {
        assert_eq!(format_bytes(512), "512 B");
        assert_eq!(format_bytes(2048), "2.0 KiB");
        assert_eq!(format_bytes(5 * 1024 * 1024), "5.0 MiB");
    }

    #[test]
    fn percent_handles_zero_total() {
        assert_eq!(percent(10, 0), 0.0);
        assert!((percent(25, 100) - 25.0).abs() < f32::EPSILON);
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn parse_pmset_battery_extracts_fields() {
        let sample = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t87%; discharging; 4:12 remaining present: true";
        let battery = parse_pmset_battery(sample).expect("battery should parse");
        assert_eq!(battery.percent, Some(87.0));
        assert_eq!(battery.state.as_deref(), Some("discharging"));
        assert_eq!(
            battery.time_remaining.as_deref(),
            Some("4:12 remaining present: true")
        );
    }
}
