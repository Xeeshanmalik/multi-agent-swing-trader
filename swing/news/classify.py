"""LLM news labeling: anonymized text in, {sentiment, category, persistence} out.

The client interface is `client.classify(text) -> dict`. Invalid model output is
coerced, never passed through (contracts/data.md rule 3).
"""
from __future__ import annotations

import hashlib

import pandas as pd

from swing.news.anonymize import anonymize

CATEGORIES = ("earnings", "guidance", "analyst_rating", "legal_regulatory", "product",
              "management", "mna", "capital_markets", "macro_sector", "commentary", "other")
SENTIMENTS = ("negative", "neutral", "positive")
PERSISTENCE = ("fundamental", "non_fundamental", "unclear")

# Placeholder until step 3 freezes the real template.
PROMPT_TEMPLATE = (
    "Classify the news item about 'the company'.\n"
    "Return JSON with exactly these keys:\n"
    "sentiment: one of " + ", ".join(SENTIMENTS) + "\n"
    "category: one of " + ", ".join(CATEGORIES) + "\n"
    "persistence: one of " + ", ".join(PERSISTENCE) + "\n"
    "Text:\n{text}\n"
)
PROMPT_HASH = hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()[:16]

LABEL_COLUMNS = ["item_id", "ticker", "sentiment", "category", "persistence",
                 "prompt_hash", "model_id"]


def _coerce(out, key: str, allowed: tuple, default: str) -> str:
    v = out.get(key) if isinstance(out, dict) else None
    if isinstance(v, str):
        v = v.strip().lower()
        if v in allowed:
            return v
    return default


def coerce_label(out) -> dict:
    return {"sentiment": _coerce(out, "sentiment", SENTIMENTS, "neutral"),
            "category": _coerce(out, "category", CATEGORIES, "other"),
            "persistence": _coerce(out, "persistence", PERSISTENCE, "unclear")}


def _names_for(reference: pd.DataFrame) -> dict:
    return {r.ticker: tuple(r.company_names or ()) for r in reference.itertuples()}


def build_text(headline, body, ticker: str, names: dict, all_tickers) -> str:
    """Anonymized classifier input for one (item, ticker) pair."""
    raw = f"{headline or ''}\n{body or ''}".strip()
    others = []
    for t in all_tickers:
        if t != ticker:
            others.append(t)
            others.extend(names.get(t, ()))
    return anonymize(raw, ticker, names.get(ticker, ()), other_names=others)


def classify_items(news: pd.DataFrame, reference: pd.DataFrame, client, model_id: str) -> pd.DataFrame:
    """One label row per (item, ticker). The client only receives anonymized text."""
    names = _names_for(reference)
    rows = []
    for r in news.itertuples():
        for t in r.tickers:
            text = build_text(r.headline, r.body, t, names, r.tickers)
            lab = coerce_label(client.classify(text))
            rows.append((r.item_id, t, lab["sentiment"], lab["category"], lab["persistence"],
                         PROMPT_HASH, model_id))
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)
