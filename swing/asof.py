"""AsOfView: the only door to the data. It never shows anything after `as_of`.

Contract: contracts/data.md. Visibility rules:
  prices      available_at   <= as_of
  news        first_seen_at  <= as_of   (published_at is NOT a visibility field)
  news_labels visible iff their news item is visible
  reference   static
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from swing import config

_NEWS_COLS = ["item_id", "tickers", "headline", "body", "source", "published_at", "first_seen_at"]
_LABEL_COLS = ["item_id", "ticker", "sentiment", "category", "persistence", "prompt_hash", "model_id"]


def _empty(cols):
    return pd.DataFrame({c: [] for c in cols})


class InMemorySource:
    """Holds the full tables. Only AsOfView should read from it."""

    def __init__(self, prices: pd.DataFrame, reference: pd.DataFrame,
                 news: pd.DataFrame | None = None, news_labels: pd.DataFrame | None = None):
        self._prices = prices.copy()
        self._prices["available_at"] = pd.to_datetime(self._prices["available_at"], utc=True)
        self._reference = reference.copy()
        self._news = _empty(_NEWS_COLS) if news is None else news.copy()
        for col in ("published_at", "first_seen_at"):
            if col in self._news:
                self._news[col] = pd.to_datetime(self._news[col], utc=True)
        self._labels = _empty(_LABEL_COLS) if news_labels is None else news_labels.copy()

    # Raw accessors, used by AsOfView (a parquet source implements the same four).
    def load_prices(self, as_of: pd.Timestamp) -> pd.DataFrame:
        p = self._prices
        return p[p["available_at"] <= as_of]

    def load_reference(self) -> pd.DataFrame:
        return self._reference

    def load_news(self, as_of: pd.Timestamp) -> pd.DataFrame:
        n = self._news
        return n[n["first_seen_at"] <= as_of]

    def load_news_labels(self) -> pd.DataFrame:
        return self._labels


class AsOfView:
    def __init__(self, source, as_of: datetime):
        config.assert_released(as_of)       # raises ValueError (naive) / SealedPeriodError
        self.source = source
        self.as_of = as_of
        self._ts = pd.Timestamp(as_of).tz_convert("UTC")

    def prices(self) -> pd.DataFrame:
        return self.source.load_prices(self._ts).copy()

    def reference(self) -> pd.DataFrame:
        return self.source.load_reference().copy()

    def news(self) -> pd.DataFrame:
        return self.source.load_news(self._ts).copy()

    def news_labels(self) -> pd.DataFrame:
        lab = self.source.load_news_labels()
        visible = set(self.source.load_news(self._ts)["item_id"])
        return lab[lab["item_id"].isin(visible)].copy()
