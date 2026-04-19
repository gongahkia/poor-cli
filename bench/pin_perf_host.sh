#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "perf-host-pin: skip (non-linux)"
  exit 0
fi

write_root_file() {
  local value="$1"
  local path="$2"
  if [[ ! -w "${path}" ]]; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1; then
    printf "%s" "${value}" | sudo tee "${path}" >/dev/null || true
  else
    printf "%s" "${value}" >"${path}" || true
  fi
}

for governor_file in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [[ -e "${governor_file}" ]] || continue
  write_root_file "performance" "${governor_file}"
done

if [[ -e /sys/devices/system/cpu/intel_pstate/no_turbo ]]; then
  write_root_file "1" "/sys/devices/system/cpu/intel_pstate/no_turbo"
fi

echo "perf-host-pin: applied best-effort cpu governor/turbo settings"
