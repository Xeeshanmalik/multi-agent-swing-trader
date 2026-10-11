"""FROZEN. Frozen files must match FROZEN.sha256 (written by `make freeze`)."""
import hashlib
from pathlib import Path

import pytest

MANIFEST = Path("FROZEN.sha256")


def _entries():
    if not MANIFEST.exists():
        return []
    out = []
    for line in MANIFEST.read_text().splitlines():
        if line.strip():
            digest, path = line.split(maxsplit=1)
            out.append((digest, path.lstrip("*")))
    return out


@pytest.mark.skipif(not MANIFEST.exists(), reason="run `make freeze` first")
@pytest.mark.parametrize("digest,path", _entries())
def test_frozen_file_unchanged(digest, path):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert actual == digest, f"{path} changed. Frozen files are owner-only."
