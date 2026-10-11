"""Point-in-time liquidity universe (contracts/data.md `members`)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from swing import config

COLUMNS = ["ticker", "adv_rank", "sector"]


def members(view, signal_date: date) -> pd.DataFrame:
    """Top-N names by median dollar volume over the last ADV_LOOKBACK bars <= signal_date.

    Uses only bars visible in `view`. Requires a bar on signal_date, close >= MIN_PRICE
    and at least MIN_HISTORY visible sessions up to and including signal_date.
    """
    p = view.prices()
    p = p[p["date"] <= signal_date]
    empty = pd.DataFrame({"ticker": pd.Series(dtype=str), "adv_rank": pd.Series(dtype=int),
                          "sector": pd.Series(dtype=str)})
    if p.empty:
        return empty
    p = p.sort_values(["ticker", "date"])
    g = p.groupby("ticker", sort=True)
    n_hist = g["date"].size()
    last = g.tail(1).set_index("ticker")
    ok = (last["date"] == signal_date) & (last["close"] >= config.MIN_PRICE) \
        & (n_hist.reindex(last.index) >= config.MIN_HISTORY)
    keep = ok[ok].index
    if len(keep) == 0:
        return empty
    q = p[p["ticker"].isin(keep)].copy()
    q["dv"] = q["close"] * q["volume"]
    recent = q.groupby("ticker").tail(config.ADV_LOOKBACK)
    adv = recent.groupby("ticker")["dv"].median()
    out = adv.rename("adv").reset_index().sort_values(["adv", "ticker"], ascending=[False, True])
    out = out.head(config.UNIVERSE_TOP_N).reset_index(drop=True)
    out["adv_rank"] = range(1, len(out) + 1)
    sec = view.reference().set_index("ticker")["sector"]
    out["sector"] = out["ticker"].map(sec)
    return out[COLUMNS]
