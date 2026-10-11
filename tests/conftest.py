"""FROZEN. Shared test helpers: deterministic synthetic data, no network.

Modules that don't exist yet are skipped so agents can build step by step.
`make test` sets STRICT_TESTS=1, which turns those skips into failures.
"""
from __future__ import annotations

import importlib
import os
from datetime import date, datetime, time, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from swing import config

STRICT = os.environ.get("STRICT_TESTS") == "1"

SECTORS = ("Tech", "Health", "Financials", "Energy", "Consumer", "Industrials")
CATEGORIES = ("earnings", "guidance", "analyst_rating", "legal_regulatory", "product",
              "management", "mna", "capital_markets", "macro_sector", "commentary", "other")
PHRASES = ("shares slide after analyst downgrade", "falls as sector sells off",
           "drops on recall report", "slumps after guidance cut", "rallies on new contract",
           "dips amid market jitters", "faces regulatory probe", "beats expectations")
SYLLABLES = ("Vor", "Qua", "Zen", "Tal", "Mir", "Kex", "Dra", "Pol", "Wyn", "Jor", "Bex", "Lum")
LETTERS = "QXZJKVWY"


def require(modname: str):
    """Import a module the agents are expected to build; skip (or fail if strict) if absent."""
    try:
        return importlib.import_module(modname)
    except ModuleNotFoundError as e:
        missing = e.name or ""
        if modname == missing or modname.startswith(missing + "."):
            msg = f"{modname} not implemented yet"
            if STRICT:
                pytest.fail(msg + " (STRICT_TESTS=1)")
            pytest.skip(msg)
        raise


def utc(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=config.MARKET_TZ).astimezone(timezone.utc)


# ----------------------------------------------------------- synthetic data
def make_frames(seed: int = 0, n_tickers: int = 48, n_days: int = 420,
                start: str = "2021-01-04", drop_rate: float = 0.012,
                news_per_day: int = 18, n_delisted: int = 4) -> dict:
    """Random walks with planted one-day drops, noisy news and random labels.

    Returns dict with prices, reference, news, news_labels. There is no real
    signal: labels and news are unrelated to subsequent returns.
    """
    rng = np.random.default_rng(seed)
    days = [d.date() for d in pd.bdate_range(start, periods=n_days)]

    tickers, seen = [], set()
    while len(tickers) < n_tickers:
        t = "".join(rng.choice(list(LETTERS), 4))
        if t not in seen:
            seen.add(t)
            tickers.append(t)

    ref_rows = []
    delist_idx = {}
    for i, t in enumerate(tickers):
        base = SYLLABLES[i % len(SYLLABLES)] + SYLLABLES[(i * 7 + 3) % len(SYLLABLES)].lower()
        names = (f"{base} Corp {i}", f"{base} Holdings {i}")
        if i < n_delisted:
            delist_idx[t] = int(rng.integers(300, n_days - 15))
        ref_rows.append((t, names, SECTORS[i % len(SECTORS)], days[0],
                         days[delist_idx[t]] if t in delist_idx else None))
    reference = pd.DataFrame(ref_rows, columns=["ticker", "company_names", "sector",
                                                "list_date", "delist_date"])

    sector_f = {s: rng.normal(0, 0.008, n_days) for s in SECTORS}
    rows, drops = [], set()
    for i, t in enumerate(tickers):
        px = 3.0 if i == n_tickers - 1 else 20.0 + 150.0 * rng.random()  # last ticker: low price
        vol_scale = float(rng.uniform(5e5, 5e6))
        last = delist_idx.get(t, n_days - 1)
        sec = SECTORS[i % len(SECTORS)]
        for k, d in enumerate(days[: last + 1]):
            r = rng.normal(0, 0.015) + sector_f[sec][k]
            if k > 25 and rng.random() < drop_rate:
                r -= 0.07
                drops.add((t, d))
            o = px * (1 + rng.normal(0, 0.004))
            c = px * (1 + r)
            h = max(o, c) * (1 + abs(rng.normal(0, 0.003)))
            lo = min(o, c) * (1 - abs(rng.normal(0, 0.003)))
            rows.append((t, d, o, h, lo, c, vol_scale * float(rng.lognormal(0, 0.3)),
                         config.bar_available_at(d)))
            px = c
    prices = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close",
                                         "volume", "available_at"])
    prices["available_at"] = pd.to_datetime(prices["available_at"], utc=True)

    names = dict(zip(reference["ticker"], reference["company_names"]))
    live = {d: [t for t in tickers if d <= days[delist_idx.get(t, n_days - 1)]] for d in days}
    news_rows, k = [], 0

    def add_item(t, d, seen_at):
        nonlocal k
        nm = names[t][int(rng.integers(2))]
        style = int(rng.integers(3))
        phrase = PHRASES[int(rng.integers(len(PHRASES)))]
        if style == 0:
            head = f"{nm} ({t}) {phrase}"
        elif style == 1:
            head = f"${t}: {nm.upper()} {phrase}"
        else:
            head = f"{nm}'s stock {phrase}"
        body = f"Analysts covering {nm} said {t} {phrase}." if rng.random() < 0.5 else ""
        pub = seen_at - timedelta(minutes=int(rng.integers(0, 120)))
        news_rows.append((f"n{k}", (t,), head, body, "wire", pub, seen_at))
        k += 1

    for d in days:
        for _ in range(news_per_day):
            if not live[d]:
                break
            t = live[d][int(rng.integers(len(live[d])))]
            add_item(t, d, utc(d, 0) + timedelta(minutes=int(rng.integers(0, 24 * 60))))
        for t in live[d]:
            if (t, d) in drops and rng.random() < 0.8:
                add_item(t, d, utc(d, 9, 30) + timedelta(minutes=int(rng.integers(0, 360))))
    news = pd.DataFrame(news_rows, columns=["item_id", "tickers", "headline", "body", "source",
                                            "published_at", "first_seen_at"])
    for col in ("published_at", "first_seen_at"):
        news[col] = pd.to_datetime(news[col], utc=True)

    news_labels = random_labels(news, rng)
    return {"prices": prices, "reference": reference, "news": news, "news_labels": news_labels}


def random_labels(news: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    for item_id, tks in zip(news["item_id"], news["tickers"]):
        for t in tks:
            rows.append((item_id, t,
                         rng.choice(["negative", "neutral", "positive"], p=[0.45, 0.3, 0.25]),
                         CATEGORIES[int(rng.integers(len(CATEGORIES)))],
                         rng.choice(["fundamental", "non_fundamental", "unclear"], p=[0.35, 0.45, 0.2]),
                         "synthetic", "stub-model"))
    return pd.DataFrame(rows, columns=["item_id", "ticker", "sentiment", "category",
                                       "persistence", "prompt_hash", "model_id"])


def copy_frames(frames: dict) -> dict:
    return {k: v.copy(deep=True) for k, v in frames.items()}


def perturb_future(frames: dict, as_of: datetime, seed: int) -> dict:
    """Scramble everything that becomes visible after `as_of` and plant tempting future items."""
    rng = np.random.default_rng(seed)
    out = copy_frames(frames)
    ts = pd.Timestamp(as_of)

    p = out["prices"]
    fut = p["available_at"] > ts
    n = int(fut.sum())
    f = rng.uniform(0.5, 1.5, n)
    for col in ("open", "high", "low", "close"):
        p.loc[fut, col] = p.loc[fut, col].to_numpy() * f
    p.loc[fut, "volume"] = p.loc[fut, "volume"].to_numpy() * rng.uniform(0.1, 10.0, n)

    # Flip labels of items first seen after the cutoff.
    late_ids = set(out["news"].loc[out["news"]["first_seen_at"] > ts, "item_id"])
    lab = out["news_labels"]
    m = lab["item_id"].isin(late_ids)
    lab.loc[m, "persistence"] = rng.choice(["fundamental", "non_fundamental"], int(m.sum()))
    lab.loc[m, "sentiment"] = "negative"

    # Items published BEFORE the cutoff but first seen AFTER it: must stay invisible.
    tickers = sorted(p["ticker"].unique())
    add_news, add_lab = [], []
    for i, t in enumerate(tickers):
        iid = f"future-{seed}-{i}"
        add_news.append((iid, (t,), f"{t} fraud probe widens", "", "wire",
                         as_of - timedelta(hours=2), as_of + timedelta(minutes=1 + i)))
        add_lab.append((iid, t, "negative", "legal_regulatory",
                        "fundamental" if i % 2 else "non_fundamental", "synthetic", "stub-model"))
    an = pd.DataFrame(add_news, columns=out["news"].columns)
    for col in ("published_at", "first_seen_at"):
        an[col] = pd.to_datetime(an[col], utc=True)
    out["news"] = pd.concat([out["news"], an], ignore_index=True)
    out["news_labels"] = pd.concat([lab, pd.DataFrame(add_lab, columns=lab.columns)],
                                   ignore_index=True)
    return out


FORCED = dict(z_max=-0.5, ret_max=0.0, buckets=("NF", "F", "NN", "OTHER"), max_picks=4)


def forced_params():
    types = require("swing.strategy.types")
    return types.StrategyParams(**FORCED)


def candidate_key(c):
    return (c.ticker, c.signal_date, c.entry_date, c.bucket, c.news_item_ids,
            round(c.drop_ret, 12), round(c.drop_z, 9), round(c.range_pos20, 9), c.adv_rank,
            round(c.prob_beat_bench, 9), round(c.exp_excess, 12))


def assert_decisions_equal(a, b) -> None:
    assert a.entry_date == b.entry_date and a.as_of == b.as_of
    assert [candidate_key(c) for c in a.candidates] == [candidate_key(c) for c in b.candidates]
    assert [c.ticker for c in a.picks] == [c.ticker for c in b.picks], "picks changed"


def assert_scans_equal(a, b) -> None:
    assert a.signal_date == b.signal_date and a.as_of == b.as_of
    assert [candidate_key(c) for c in a.candidates] == [candidate_key(c) for c in b.candidates]


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="session", autouse=True)
def _session_trials_log(tmp_path_factory):
    """Set before any module-scoped fixture runs, so tests never touch ledger/trials.jsonl."""
    old = os.environ.get("SWING_TRIALS_LOG")
    os.environ["SWING_TRIALS_LOG"] = str(tmp_path_factory.mktemp("ledger") / "trials.jsonl")
    yield
    if old is None:
        os.environ.pop("SWING_TRIALS_LOG", None)
    else:
        os.environ["SWING_TRIALS_LOG"] = old


@pytest.fixture(autouse=True)
def _isolated_trials_log(tmp_path, monkeypatch):
    monkeypatch.setenv("SWING_TRIALS_LOG", str(tmp_path / "trials.jsonl"))


@pytest.fixture(scope="session")
def frames():
    return make_frames()


@pytest.fixture(scope="session")
def sessions(frames):
    return sorted(frames["prices"]["date"].unique())


@pytest.fixture
def asof():
    return require("swing.asof")


@pytest.fixture
def signals():
    return require("swing.strategy.signals")


@pytest.fixture
def source(asof, frames):
    return asof.InMemorySource(**copy_frames(frames))


def build_source(frames_: dict):
    asof = require("swing.asof")
    return asof.InMemorySource(**copy_frames(frames_))
