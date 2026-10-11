"""Parquet-backed source with the same interface as swing.asof.InMemorySource.

Layout under `root` (default data/derived/): prices.parquet, reference.parquet,
and optionally news.parquet, news_labels.parquet. Tuple columns (company_names,
tickers) round-trip as lists and are converted back to tuples on load.
AsOfView does the visibility filtering; this class only loads.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from swing.asof import InMemorySource

ROOT = Path(__file__).resolve().parents[2]
DERIVED = ROOT / "data" / "derived"
_TUPLE_COLS = ("company_names", "tickers")


def write_tables(root: Path, prices, reference, news=None, news_labels=None) -> None:
    """Write derived tables. Refuses to overwrite existing files (derive into a new dir)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, df in (("prices", prices), ("reference", reference),
                     ("news", news), ("news_labels", news_labels)):
        if df is None:
            continue
        path = root / f"{name}.parquet"
        if path.exists():
            raise FileExistsError(f"{path} exists; write derived tables to a new directory")
        out = df.copy()
        for c in _TUPLE_COLS:
            if c in out:
                out[c] = out[c].map(lambda v: list(v) if v is not None else None)
        out.to_parquet(path, index=False)


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    for c in _TUPLE_COLS:
        if c in df:
            df[c] = df[c].map(lambda v: tuple(v) if v is not None else ())
    return df


class ParquetSource(InMemorySource):
    def __init__(self, root: Path | str = DERIVED):
        root = Path(root)
        prices, reference = _read(root / "prices.parquet"), _read(root / "reference.parquet")
        if prices is None or reference is None:
            raise FileNotFoundError(f"prices.parquet / reference.parquet missing under {root}")
        if "date" in prices:
            prices["date"] = pd.to_datetime(prices["date"]).dt.date
        for c in ("list_date", "delist_date"):
            if c in reference:
                reference[c] = reference[c].map(lambda v: None if pd.isna(v) else pd.Timestamp(v).date())
        super().__init__(prices, reference, _read(root / "news.parquet"),
                         _read(root / "news_labels.parquet"))
