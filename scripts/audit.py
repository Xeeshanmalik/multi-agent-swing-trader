#!/usr/bin/env python3
"""FROZEN. Checks that frozen files are unchanged and the trial ledger was only ever appended to."""
import hashlib
import subprocess
import sys
from pathlib import Path

ok = True
manifest = Path("FROZEN.sha256")
if not manifest.exists():
    print("FROZEN.sha256 missing: the owner runs `make freeze` after review.")
    ok = False
else:
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, path = line.split(maxsplit=1)
        path = path.lstrip("*")
        p = Path(path)
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            print(f"CHANGED: {path}")
            ok = False
    if ok:
        print("Frozen files intact.")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


ledger = "ledger/trials.jsonl"
commits = git("log", "--reverse", "--format=%H", "--", ledger).split()
versions = [git("show", f"{c}:{ledger}") for c in commits]
if Path(ledger).exists():
    versions.append(Path(ledger).read_text())
for older, newer in zip(versions, versions[1:]):
    if not newer.startswith(older):
        print("LEDGER REWRITTEN: ledger/trials.jsonl lost or changed earlier lines.")
        ok = False
        break
else:
    n = sum(1 for line in (versions[-1] if versions else "").splitlines() if line.strip())
    print(f"Trial ledger append-only across {len(commits)} commits; {n} trials logged.")
sys.exit(0 if ok else 1)
