#!/usr/bin/env python3
"""PreToolUse guard for Edit/Write/MultiEdit/NotebookEdit.

1. Frozen paths: denied for every agent, always.
2. Ownership: when Claude Code reports which agent is acting (agent_type),
   that agent may write only inside its own paths.
Writes outside the project (e.g. /tmp scratch files) are left to the normal
permission rules. This is a guard rail, not a sandbox: Bash can still write
files, which is why `make audit` and git history are the final check.
"""
import fnmatch
import json
import os
import sys
from pathlib import Path

FROZEN = [
    "contracts/*", "swing/config.py", "swing/env.py", "docs/PREREGISTRATION.md",
    "tests/conftest.py", "tests/leakage/*", "tests/test_frozen.py", "Makefile",
    "scripts/start-team.sh", "scripts/audit.py", ".claude/*", "FROZEN.sha256",
    "ledger/trials.jsonl", ".env", ".env.*",
]
OWNERS = {
    "market-data": ["swing/asof.py", "swing/data/*", "scripts/data/*", "tests/data/*",
                    "docs/gates/gate0-data*"],
    "news-intel": ["swing/news/*", "scripts/news/*", "tests/news/*", "docs/gates/gate0-news*"],
    "quant": ["swing/strategy/*", "swing/cli.py", "swing/research/*", "tests/strategy/*",
              "ledger/*", "docs/gates/gate1-*", "docs/gates/gate3-*"],
    "auditor": ["tests/audit/*", "docs/audits/*"],
}


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    ti = data.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path") or ""
    if not raw:
        sys.exit(0)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()
    path = Path(raw)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        sys.exit(0)  # outside the project
    match = lambda pats: any(fnmatch.fnmatch(rel, p) for p in pats)
    if match(FROZEN):
        deny(f"{rel} is frozen. Only the owner edits it. Send the lead your evidence instead.")
    agent = data.get("agent_type") or ""
    if agent in OWNERS and not match(OWNERS[agent]):
        deny(f"{rel} is not owned by {agent}. Message the owning agent instead (see CLAUDE.md).")
    sys.exit(0)


if __name__ == "__main__":
    main()
