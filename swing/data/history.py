"""Survivorship-free price history and reference table, built from per-date snapshots.

Pure functions on DataFrames (no network, no key). Inputs come from
`MassiveClient.grouped_daily` (one frame per session, every ticker that traded)
and `MassiveClient.tickers_on` (one frame per snapshot date). The set of tickers
is whatever traded on each date, never today's ticker list.

Identity: a stable `company_id` (CIK, else composite FIGI, else a symbol
fallback) is attached to every bar, so renames keep one id and a reused symbol
gets two. Corporate actions are applied per (ticker, company_id).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from swing import config

PRICE_COLS = ["ticker", "date", "open", "high", "low", "close", "volume", "available_at"]
SECTORS = ("Tech", "Health", "Financials", "Energy", "Consumer", "Industrials",
           "Materials", "Utilities", "RealEstate", "Telecom", "Staples")


# ------------------------------------------------------------------ identity
def company_id(row) -> str:
    for k in ("cik", "composite_figi"):
        v = row.get(k) if hasattr(row, "get") else None
        if isinstance(v, str) and v.strip():
            return f"{k.split('_')[-1].upper()}:{v.strip()}"
    return f"SYM:{row.get('ticker')}"


def identity_table(ticker_snaps: pd.DataFrame) -> pd.DataFrame:
    """ticker_snaps: ticker, snapshot_date, name, cik?, composite_figi? ->
    ticker, snapshot_date (date), company_id, name; one row per ticker per snapshot."""
    t = ticker_snaps.copy()
    for c in ("cik", "composite_figi", "name"):
        if c not in t:
            t[c] = None
    t["company_id"] = [company_id(r) for r in t.to_dict("records")]
    t["snapshot_date"] = pd.to_datetime(t["snapshot_date"]).dt.date
    return t[["ticker", "snapshot_date", "company_id", "name"]].drop_duplicates(
        ["ticker", "snapshot_date"]).sort_values(["ticker", "snapshot_date"]).reset_index(drop=True)


def attach_company_id(bars: pd.DataFrame, ident: pd.DataFrame) -> pd.DataFrame:
    """Give every bar the company_id from the nearest earlier snapshot of that ticker
    (else the nearest later one; else the symbol fallback)."""
    b = bars.copy()
    b["_d"] = pd.to_datetime(b["date"])
    i = ident.assign(_d=pd.to_datetime(ident["snapshot_date"]))[["ticker", "_d", "company_id"]]
    b = b.sort_values("_d")
    i = i.sort_values("_d")
    back = pd.merge_asof(b, i.rename(columns={"company_id": "cid_b"}), on="_d", by="ticker",
                         direction="backward")
    fwd = pd.merge_asof(b[["ticker", "_d"]], i.rename(columns={"company_id": "cid_f"}), on="_d",
                        by="ticker", direction="forward")
    cid = back["cid_b"].astype(object).where(back["cid_b"].notna(), fwd["cid_f"].astype(object).values)
    back["company_id"] = cid.where(cid.notna(), "SYM:" + back["ticker"].astype(str))
    return back.drop(columns=["_d", "cid_b"]).sort_values(["ticker", "date"]).reset_index(drop=True)


# ----------------------------------------------------------------- adjusting
def adjust_for_actions(bars: pd.DataFrame, splits: pd.DataFrame | None,
                       dividends: pd.DataFrame | None = None) -> pd.DataFrame:
    """Backward-adjust OHLC and volume for splits and cash dividends.

    bars needs ticker, company_id, date, open, high, low, close, volume.
    splits: ticker, execution_date, split_from, split_to.
    dividends: ticker, ex_dividend_date, cash_amount.
    An action on date X changes bars dated strictly before X, for that ticker
    and the company that held the ticker on X (so a reused symbol is untouched).
    Dividend factor = 1 - cash / previous close (previous close is split-adjusted
    to the same basis first).
    """
    b = bars.sort_values(["ticker", "date"]).reset_index(drop=True).copy()
    b["date"] = pd.to_datetime(b["date"]).dt.date
    px = ["open", "high", "low", "close"]
    b["_f"] = 1.0       # multiplicative price factor
    b["_v"] = 1.0       # volume factor

    def owner(t, d):
        s = b[(b["ticker"] == t)]
        on = s[s["date"] >= d]
        if len(on):
            return on.iloc[0]["company_id"]
        return s.iloc[-1]["company_id"] if len(s) else None

    if splits is not None and len(splits):
        for r in splits.to_dict("records"):
            x = pd.Timestamp(r["execution_date"]).date()
            ratio = float(r["split_from"]) / float(r["split_to"])
            if not np.isfinite(ratio) or ratio <= 0:
                continue
            cid = owner(r["ticker"], x)
            m = (b["ticker"] == r["ticker"]) & (b["company_id"] == cid) & (b["date"] < x)
            b.loc[m, "_f"] *= ratio
            b.loc[m, "_v"] /= ratio
    if dividends is not None and len(dividends):
        for r in dividends.to_dict("records"):
            x = pd.Timestamp(r["ex_dividend_date"]).date()
            cash = float(r["cash_amount"])
            prev = b[(b["ticker"] == r["ticker"]) & (b["date"] < x)]
            if prev.empty or cash <= 0:
                continue
            cid = owner(r["ticker"], x)
            prev = prev[prev["company_id"] == cid]
            if prev.empty:
                continue
            last = prev.iloc[-1]
            pc = float(last["close"]) * float(last["_f"])
            if pc <= 0 or cash >= pc:
                continue
            m = (b["ticker"] == r["ticker"]) & (b["company_id"] == cid) & (b["date"] < x)
            b.loc[m, "_f"] *= 1.0 - cash / pc
    for c in px:
        b[c] = b[c].astype(float) * b["_f"]
    b["volume"] = b["volume"].astype(float) * b["_v"]
    return b.drop(columns=["_f", "_v"])


def build_prices(snapshots: pd.DataFrame, ticker_snaps: pd.DataFrame,
                 splits: pd.DataFrame | None = None,
                 dividends: pd.DataFrame | None = None) -> pd.DataFrame:
    """snapshots: concatenated per-date grouped bars (ticker,date,open..volume).
    Returns contract `prices` plus a `company_id` column (extra columns are allowed
    and ignored by AsOfView consumers)."""
    s = snapshots.dropna(subset=["close"]).drop_duplicates(["ticker", "date"], keep="last")
    s = attach_company_id(s, identity_table(ticker_snaps))
    s = adjust_for_actions(s, splits, dividends)
    s["available_at"] = pd.to_datetime([config.bar_available_at(d) for d in s["date"]], utc=True)
    return s[PRICE_COLS + ["company_id"]].sort_values(["ticker", "date"]).reset_index(drop=True)


# ----------------------------------------------------------------- reference
def sic_to_sector(sic) -> str | None:
    """Static, coarse SIC -> 11 GICS-style sectors (known limitation: not point-in-time).
    Rules are checked in order; unknown codes fall back to Industrials."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return None
    rules = (
        ("Energy", lambda: s in (1311, 1381, 1382, 1389, 2911, 2990, 4610)),
        ("Health", lambda: s in (2833, 2834, 2835, 2836, 3841, 3842, 3844, 3845, 3826)
                 or 8000 <= s < 8100),
        ("Telecom", lambda: s in (4812, 4813, 4822, 4841, 4899)),
        ("Utilities", lambda: 4900 <= s < 5000),
        ("RealEstate", lambda: 6500 <= s < 6600 or s == 6798),
        ("Financials", lambda: 6000 <= s < 6800),
        ("Tech", lambda: 3570 <= s < 3580 or 3660 <= s < 3700 or 7370 <= s < 7380
                 or s in (3812, 3827)),
        ("Staples", lambda: 100 <= s < 1000 or 2000 <= s < 2200 or s in (5400, 5411, 5412)),
        ("Materials", lambda: 1000 <= s < 1500 or 2600 <= s < 2700 or 2800 <= s < 2900
                 or 3300 <= s < 3400),
        ("Consumer", lambda: 2200 <= s < 2600 or 3000 <= s < 3200 or 3900 <= s < 4000
                 or 5200 <= s < 6000 or 7000 <= s < 7300 or 7800 <= s < 7900
                 or s in (3630, 3651, 3711)),
    )
    for name, test in rules:
        if test():
            return name
    return "Industrials"


def build_reference(prices: pd.DataFrame, ticker_snaps: pd.DataFrame,
                    sic_by_ticker: dict | None = None) -> pd.DataFrame:
    """One row per ticker. list/delist dates come from the bars themselves:
    list_date = first bar, delist_date = last bar unless the ticker traded on the
    final session in `prices` (then null). company_names is every name seen for
    any company that held the ticker. Extra columns: company_id (latest),
    n_companies (>1 means the symbol was reused)."""
    last_session = prices["date"].max()
    g = prices.sort_values("date").groupby("ticker")
    first, last = g["date"].first(), g["date"].last()
    n_co = g["company_id"].nunique()
    cid = g["company_id"].last()
    names = {}
    if "name" in ticker_snaps:
        for t, nm in zip(ticker_snaps["ticker"], ticker_snaps["name"]):
            if isinstance(nm, str) and nm:
                names.setdefault(t, [])
                if nm not in names[t]:
                    names[t].append(nm)
    sic = sic_by_ticker or {}
    rows = []
    for t in first.index:
        rows.append((t, tuple(names.get(t, ())), sic_to_sector(sic.get(t)) or "Industrials",
                     first[t], None if last[t] >= last_session else last[t], cid[t], int(n_co[t])))
    return pd.DataFrame(rows, columns=["ticker", "company_names", "sector", "list_date",
                                       "delist_date", "company_id", "n_companies"])
