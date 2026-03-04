#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAST_MODE=0

for arg in "$@"; do
  case "$arg" in
    --fast)
      FAST_MODE=1
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./scripts/acceptance_walkthrough.sh [--fast]

Runs a quick acceptance prep and prints a guided manual walkthrough for:
- solo terminal-agent commands
- multiplayer host/join/lobby/handoff/token lifecycle

Options:
  --fast    Skip cargo/pytest execution and print only the walkthrough.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"

echo "== poor-cli acceptance walkthrough =="
echo "repo: $ROOT_DIR"
echo

if [[ "$FAST_MODE" -eq 0 ]]; then
  echo "[1/3] Running Rust TUI tests..."
  (cd poor-cli-tui && cargo test -q)
  echo "[2/3] Running Python tests..."
  pytest -q
  echo "[3/3] Sanity checks passed."
else
  echo "[fast] Skipping automated test execution."
fi

cat <<'EOF'

==============================
Manual Acceptance Walkthrough
==============================

Use 3 terminals.

Terminal A (Host / Owner)
1. Run:
   make run
2. In TUI, run:
   /doctor
   /bootstrap
   /profile safe
   /context-budget 6000
   /focus start Ship multiplayer+solo acceptance || keep queue serialized || all checks green
   /workspace-map
   /tasks add Verify host controls and role transitions
   /qa start
   /host-server
   /host-server preset pairing
   /host-server lobby on
   /host-server share viewer
   /host-server share prompter
3. Copy both invite codes from share output.

Terminal B (Viewer)
1. Run:
   make run
2. In TUI, join with wizard:
   /join-server
   (enter ws://... URL)
   (enter room)
   (enter viewer token)
3. Expected:
   - initially pending if lobby is on
   - cannot run prompt actions until approved

Terminal C (Prompter Candidate)
1. Run:
   make run
2. In TUI, join:
   /join-server <prompter invite code>

Back to Terminal A (Host controls)
1. Approve both:
   /host-server members
   /host-server approve <viewer-connection-id>
   /host-server approve <prompter-connection-id>
2. Confirm role updates / room HUD:
   /status
   /host-server members
3. Handoff flow:
   /host-server handoff <connection-id>
4. Token lifecycle:
   /host-server rotate-token viewer 120
   /host-server revoke <token-or-connection-id>
5. Activity timeline:
   /host-server activity
   /host-server activity default 50 member_joined

Solo flow check (any terminal)
1. /resume
2. /explain-diff
3. /fix-failures pytest -q
4. /autopilot status
5. /tasks list
6. /focus status

Expected acceptance outcomes
- Room events and member role updates visible in status/hints.
- Lobby approvals gate pending users correctly.
- Handoff keeps single active prompter.
- Rotated/revoked tokens are enforced.
- Solo commands are available and persisted where applicable.
- QA mode emits PASS/FAIL deltas as files change.
EOF
