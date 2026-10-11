#!/usr/bin/env bash
# FROZEN. Start (or re-attach to) the team in tmux. Usage: ./scripts/start-team.sh
set -euo pipefail
SESSION="${SWING_TMUX_SESSION:-swing}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v tmux >/dev/null || { echo "tmux is not installed (apt install tmux)"; exit 1; }
command -v claude >/dev/null || { echo "Claude Code is not installed (curl -fsSL https://claude.ai/install.sh | bash)"; exit 1; }
[ -f .env ] || echo "Note: no .env yet. Data agents will stop when they need API keys (see .env.example)."

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists; attaching. (To start over: tmux kill-session -t $SESSION)"
  exec tmux attach -t "$SESSION"
fi

# Pane 0 is the lead. Teammates open in new panes when the lead spawns them.
tmux new-session -d -s "$SESSION" -n team -c "$ROOT" -x 240 -y 60
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" pane-border-status top
tmux set-option -t "$SESSION" pane-border-format " #{pane_index}: #{pane_title} "
tmux select-pane -t "$SESSION:team.0" -T lead
tmux send-keys -t "$SESSION:team.0" \
  "claude --model opus --teammate-mode tmux 'Read .claude/kickoff-prompt.md and follow it exactly.'" Enter

if [ -n "${TMUX:-}" ]; then
  tmux switch-client -t "$SESSION"
else
  exec tmux attach -t "$SESSION"
fi
