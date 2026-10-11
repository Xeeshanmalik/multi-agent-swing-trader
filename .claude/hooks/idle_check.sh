#!/usr/bin/env bash
# TeammateIdle hook: a teammate can't go idle while fast tests fail.
# Exit 2 sends stderr back to the teammate and keeps it working. To avoid an
# endless loop on a failure the teammate can't fix (e.g. in another agent's
# folder), it is blocked at most twice in a row, then allowed to idle.
input="$(cat)"
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
key="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    d={}
print(d.get("teammate_name") or d.get("agent_id") or d.get("session_id") or "unknown")' 2>/dev/null)"
state="${TMPDIR:-/tmp}/swing-idle-$(printf '%s' "$key" | tr -c 'A-Za-z0-9_-' '_')"

if out="$(timeout 600 make -s test-fast 2>&1)"; then
  rm -f "$state"
  exit 0
fi
count=$(( $(cat "$state" 2>/dev/null || echo 0) + 1 ))
if [ "$count" -gt 2 ]; then
  rm -f "$state"
  exit 0   # tried twice; let it idle so it can report to the lead
fi
echo "$count" > "$state"
{
  echo "Fast tests are failing. Fix failures in files you own, then finish."
  echo "If the failure is in another agent's files, message that agent and the lead, then stop."
  echo "----"
  printf '%s\n' "$out" | tail -n 40
} >&2
exit 2
