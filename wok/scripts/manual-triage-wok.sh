#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_ROOT="${WOK_TRIAGE_ARTIFACTS:-$ROOT/.triage/wok-manual}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$ARTIFACT_ROOT/$STAMP"
APP_NAME="${WOK_TRIAGE_APP_NAME:-Wok}"
BINARY_PROCESS_NAME="${WOK_TRIAGE_BINARY_PROCESS_NAME:-wok}"
WINDOW_TITLE="${WOK_TRIAGE_WINDOW_TITLE:-Wok}"
TYPE_DELAY="${WOK_TRIAGE_TYPE_DELAY:-0.02}"
SCENARIO_DELAY="${WOK_TRIAGE_SCENARIO_DELAY:-1.2}"
LONG_DELAY="${WOK_TRIAGE_LONG_DELAY:-3.0}"
CARGO_PROFILE="${WOK_TRIAGE_PROFILE:-dev}"
RUN_OPTIONAL_IMAGE_PROTOCOLS="${WOK_TRIAGE_IMAGE_PROTOCOLS:-0}"
CAPTURE_SCREENSHOTS="${WOK_TRIAGE_SCREENSHOTS:-1}"
KILL_EXISTING=1

usage() {
  cat <<'USAGE'
Usage: scripts/manual-triage-wok.sh [--release] [--no-kill-existing] [--image-protocols]

Builds and launches Wok with an isolated triage config, drives a small manual
QA matrix through macOS Accessibility automation, and writes screenshots/logs to:
  .triage/wok-manual/<timestamp>/

Environment knobs:
  WOK_TRIAGE_ARTIFACTS=/path       Override artifact root.
  WOK_TRIAGE_APP_NAME=Wok          UI process name for System Events.
  WOK_TRIAGE_BINARY_PROCESS_NAME=wok Process name for pgrep/pkill/logs.
  WOK_TRIAGE_TYPE_DELAY=0.02       AppleScript keystroke delay.
  WOK_TRIAGE_SCENARIO_DELAY=1.2    Delay after normal commands.
  WOK_TRIAGE_LONG_DELAY=3.0        Delay after stress/alt-screen commands.
  WOK_TRIAGE_IMAGE_PROTOCOLS=1     Try chafa/wezterm/kitty if installed.
  WOK_TRIAGE_SCREENSHOTS=0         Drive scenarios but skip screencapture.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release)
      CARGO_PROFILE="release"
      ;;
    --no-kill-existing)
      KILL_EXISTING=0
      ;;
    --image-protocols)
      RUN_OPTIONAL_IMAGE_PROTOCOLS=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$OUT"

log() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$OUT/triage.log"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "missing required command: $1"
    exit 127
  fi
}

require_cmd cargo
require_cmd osascript
require_cmd screencapture

cat > "$OUT/config.toml" <<'CONFIG'
shell = "zsh"
font_family = "Menlo"
font_size = 24.0
scrollback_lines = 20000
input_position = "bottom"
tab_bar_orientation = "horizontal"
tab_bar_side = "top"
status_bar_visible = true
status_bar_side = "bottom"
window_opacity = 1.0
pane_border_width = 1.0
focused_pane_border_width = 2.0
floating_pane_title_height = 18.0
typewriter_effect_enabled = true
typewriter_effect_cps = 180.0
typewriter_effect_max_pending_cells = 4096
visual_effect = "none"
visual_effect_intensity = 0.5
visual_effect_animated = true
debug_overlay = true
close_on_shell_exit = true
restore_session = false
CONFIG

cat > "$OUT/drive-wok.applescript" <<'APPLESCRIPT'
on focusWok(appName, windowTitle)
  tell application "System Events"
    if not (exists process appName) then error "process not found: " & appName
    tell process appName
      set frontmost to true
      repeat 30 times
        if (count of windows) > 0 then exit repeat
        delay 0.2
      end repeat
      if (count of windows) = 0 then error "no Wok windows found"
    end tell
  end tell
end focusWok

on typeLine(appName, textValue, delaySeconds)
  tell application "System Events"
    tell process appName
      set frontmost to true
      keystroke textValue
      delay delaySeconds
      key code 36
    end tell
  end tell
end typeLine

on pressEscape(appName)
  tell application "System Events"
    tell process appName
      set frontmost to true
      key code 53
    end tell
  end tell
end pressEscape

on run argv
  set actionName to item 1 of argv
  set appName to item 2 of argv
  set windowTitle to item 3 of argv
  if actionName is "focus" then
    focusWok(appName, windowTitle)
  else if actionName is "type-line" then
    typeLine(appName, item 4 of argv, item 5 of argv as real)
  else if actionName is "escape" then
    pressEscape(appName)
  else
    error "unknown action: " & actionName
  end if
end run
APPLESCRIPT

run_osascript() {
  osascript "$OUT/drive-wok.applescript" "$@"
}

shot() {
  local name="$1"
  if [[ "$CAPTURE_SCREENSHOTS" != "1" ]]; then
    log "screenshot skipped: $name.png"
    return 0
  fi
  if screencapture -x "$OUT/$name.png" 2>"$OUT/$name.screencapture.err"; then
    log "screenshot: $name.png"
  else
    log "screenshot failed: $name.png ($(tr '\n' ' ' < "$OUT/$name.screencapture.err"))"
  fi
}

send_line() {
  local label="$1"
  local line="$2"
  local delay="${3:-$SCENARIO_DELAY}"
  log "input [$label]: $line"
  run_osascript type-line "${UI_PROCESS_NAME:-$APP_NAME}" "$WINDOW_TITLE" "$line" "$TYPE_DELAY"
  sleep "$delay"
  shot "$label"
}

if [[ "$KILL_EXISTING" == "1" ]]; then
  log "stopping existing $APP_NAME/$BINARY_PROCESS_NAME processes, if any"
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
  pkill -x "$BINARY_PROCESS_NAME" >/dev/null 2>&1 || true
  sleep 0.5
fi

log "building Wok ($CARGO_PROFILE)"
if [[ "$CARGO_PROFILE" == "release" ]]; then
  cargo build -p wok --release 2>&1 | tee "$OUT/build.log"
  BIN="$ROOT/target/release/wok"
else
  cargo build -p wok 2>&1 | tee "$OUT/build.log"
  BIN="$ROOT/target/debug/wok"
fi

APP_BUNDLE="$OUT/Wok.app"
log "creating temporary app bundle $APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
cp "$BIN" "$APP_BUNDLE/Contents/MacOS/wok"
chmod +x "$APP_BUNDLE/Contents/MacOS/wok"
cat > "$APP_BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Wok</string>
    <key>CFBundleIdentifier</key>
    <string>dev.wok.terminal.triage</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleExecutable</key>
    <string>wok</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.developer-tools</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
PLIST
plutil -lint "$APP_BUNDLE/Contents/Info.plist" >/dev/null 2>&1 || true

log "launching app bundle with isolated config $OUT/config.toml"
if ! open -n "$APP_BUNDLE" --env "WOK_CONFIG=$OUT/config.toml" --args --title "$WINDOW_TITLE" 2>"$OUT/open.err"; then
  log "open --env failed; falling back to raw executable launch"
  (
    cd "$ROOT"
    exec env WOK_CONFIG="$OUT/config.toml" "$BIN" --title "$WINDOW_TITLE"
  ) >"$OUT/wok.stdout.log" 2>"$OUT/wok.stderr.log" &
  WOK_PID=$!
fi

if [[ -z "${WOK_PID:-}" ]]; then
  for _ in $(seq 1 40); do
    WOK_PID="$(pgrep -x "$BINARY_PROCESS_NAME" | tail -1 || true)"
    if [[ -z "$WOK_PID" ]]; then
      WOK_PID="$(pgrep -x "$APP_NAME" | tail -1 || true)"
    fi
    if [[ -n "$WOK_PID" ]]; then
      break
    fi
    sleep 0.25
  done
fi
if [[ -z "$WOK_PID" ]]; then
  log "failed to find running Wok process after launch"
  exit 1
fi
printf '%s\n' "$WOK_PID" > "$OUT/wok.pid"

cleanup() {
  if [[ -n "${WOK_PID:-}" ]] && kill -0 "$WOK_PID" >/dev/null 2>&1; then
    log "stopping triage Wok pid $WOK_PID"
    kill "$WOK_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "waiting for Wok window"
UI_PROCESS_NAME="$APP_NAME"
for _ in $(seq 1 40); do
  if run_osascript focus "$UI_PROCESS_NAME" "$WINDOW_TITLE" >/dev/null 2>"$OUT/focus.err"; then
    break
  fi
  UI_PROCESS_NAME="$BINARY_PROCESS_NAME"
  if run_osascript focus "$UI_PROCESS_NAME" "$WINDOW_TITLE" >/dev/null 2>"$OUT/focus.err"; then
    break
  fi
  UI_PROCESS_NAME="$APP_NAME"
  sleep 0.25
done
if ! run_osascript focus "$UI_PROCESS_NAME" "$WINDOW_TITLE" 2>"$OUT/focus.err"; then
  log "failed to focus Wok via System Events: $(tr '\n' ' ' < "$OUT/focus.err")"
  log "grant Accessibility permission to the app running this script, then rerun"
  exit 1
fi
sleep 1
shot "00-launch"

send_line "01-basic-ls" "ls"
send_line "02-printf" "printf 'hello wok\\nworld wok\\n'"
send_line "03-seq-short" "seq 1 100"
send_line "04-find-head" "find . -maxdepth 2 -type f | head -100"
send_line "05-seq-large" "seq 1 10000" "$LONG_DELAY"
send_line "06-yes-large" "yes 'wok typewriter stress' | head -5000" "$LONG_DELAY"

if command -v nvim >/dev/null 2>&1; then
  send_line "07-nvim-open" "nvim" "$LONG_DELAY"
  send_line "08-nvim-quit" ":q" "$LONG_DELAY"
else
  log "skipping nvim scenario: nvim not installed"
fi

if [[ -f "$ROOT/README.md" ]]; then
  send_line "09-less-open" "less README.md" "$LONG_DELAY"
  run_osascript type-line "$UI_PROCESS_NAME" "$WINDOW_TITLE" "q" "$TYPE_DELAY"
  sleep "$SCENARIO_DELAY"
  shot "10-less-quit"
fi

send_line "11-ls-after-alt-screen" "ls"

if [[ "$RUN_OPTIONAL_IMAGE_PROTOCOLS" == "1" ]]; then
  if command -v chafa >/dev/null 2>&1; then
    send_line "12-chafa-smoke" "chafa --version | head -1"
  else
    log "skipping chafa scenario: chafa not installed"
  fi
  if command -v wezterm >/dev/null 2>&1; then
    send_line "13-wezterm-imgcat-smoke" "wezterm imgcat --help | head -5"
  else
    log "skipping wezterm imgcat scenario: wezterm not installed"
  fi
  if command -v kitty >/dev/null 2>&1; then
    send_line "14-kitty-icat-smoke" "kitty +kitten icat --help | head -5"
  else
    log "skipping kitty icat scenario: kitty not installed"
  fi
fi

log "capturing process sample"
sample "$WOK_PID" 1 -file "$OUT/wok.sample.txt" >/dev/null 2>&1 || true

log "capturing recent unified logs"
/usr/bin/log show --style compact --last 2m --predicate 'process == "wok" OR process == "Wok"' > "$OUT/wok.unified.log" 2>&1 || true

log "triage complete: $OUT"
echo "$OUT"
