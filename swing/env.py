"""FROZEN. Secrets come from the environment or from .env, never from code or chat.

Agents' Read tool is denied on .env; this helper lets *code* use the keys
without any agent ever seeing them. Never print or log the returned values.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv() -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    """Return the secret `name`, or raise with a message that never includes a value."""
    if name not in os.environ:
        _load_dotenv()
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is not set. The owner adds it to .env (see .env.example).")
    return value
