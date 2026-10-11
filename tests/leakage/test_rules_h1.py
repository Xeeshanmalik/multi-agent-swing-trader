"""FROZEN. The strategy must implement exactly the pre-registered H1 rule."""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from swing import config
from tests.conftest import build_source, copy_frames, forced_params, require, utc

IDX = 330  # signal date index


def _event(frames, sessions, items, ticker_index=8):
    """Plant a 9% drop for one ticker on sessions[IDX] and replace its news with `items`.

    items: list of (minutes offset or datetime, sentiment, category, persistence).
    """
    fr = copy_frames(frames)
    d, e = sessions[IDX], sessions[IDX + 1]
    ref = fr["reference"]
    t = ref[ref["delist_date"].isna()]["ticker"].iloc[ticker_index]
    p = fr["prices"]
    rows = p[p["ticker"] == t].sort_values("date")
    prev_close = float(rows[rows["date"] < d]["close"].iloc[-1])
    m = (p["ticker"] == t) & (p["date"] == d)
    o = float(p.loc[m, "open"].iloc[0])
    p.loc[m, "close"] = prev_close * 0.91
    p.loc[m, "low"] = min(o, prev_close * 0.91) * 0.997
    p.loc[m, "high"] = max(o, prev_close * 0.91) * 1.002

    lo = config.news_window_start(sessions[IDX - 1])
    hi = config.decision_time(e) + timedelta(hours=2)
    n, lab = fr["news"], fr["news_labels"]
    mine = n["tickers"].apply(lambda tk: t in tk) & (n["first_seen_at"] > pd.Timestamp(lo) - pd.Timedelta(hours=1)) \
        & (n["first_seen_at"] <= pd.Timestamp(hi))
    drop_ids = set(n.loc[mine, "item_id"])
    n = n[~n["item_id"].isin(drop_ids)]
    lab = lab[~lab["item_id"].isin(drop_ids)]
    add_n, add_l = [], []
    for j, (when, sent, cat, pers) in enumerate(items):
        iid = f"evt-{j}"
        add_n.append((iid, (t,), f"headline {j}", "", "wire", when - timedelta(minutes=5), when))
        add_l.append((iid, t, sent, cat, pers, "synthetic", "stub-model"))
    an = pd.DataFrame(add_n, columns=n.columns)
    for col in ("published_at", "first_seen_at"):
        an[col] = pd.to_datetime(an[col], utc=True)
    fr["news"] = pd.concat([n, an], ignore_index=True)
    fr["news_labels"] = pd.concat([lab, pd.DataFrame(add_l, columns=lab.columns)], ignore_index=True)
    return fr, t, d, e


def _scan(fr, d, params=None):
    return require("swing.strategy.signals").scan(build_source(fr), d, params)


def _decide(fr, e, params=None):
    return require("swing.strategy.signals").decide(build_source(fr), e, params)


def _find(result, t):
    hits = [c for c in result.candidates if c.ticker == t]
    return hits[0] if hits else None


def test_drop_metrics_match_spec(frames, sessions):
    d0 = sessions[IDX]
    fr, t, d, e = _event(frames, sessions, [(utc(d0, 11), "negative", "analyst_rating", "non_fundamental")])
    c = _find(_scan(fr, d, forced_params()), t)
    assert c is not None
    asof = require("swing.asof")
    universe = require("swing.data.universe")
    v = asof.AsOfView(build_source(fr), config.scan_time(d))
    mem = universe.members(v, d)
    p = fr["prices"]
    def ret(tk):
        r = p[p["ticker"] == tk].sort_values("date")
        r = r[r["date"] <= d]
        return float(r["close"].iloc[-1] / r["close"].iloc[-2] - 1)
    sector = mem.loc[mem["ticker"] == t, "sector"].iloc[0]
    sect_mean = np.mean([ret(tk) for tk in mem.loc[mem["sector"] == sector, "ticker"]])
    rows = p[(p["ticker"] == t) & (p["date"] <= d)].sort_values("date")
    rets = rows["close"].pct_change().to_numpy()
    sigma20 = float(np.std(rets[-21:-1], ddof=1))
    last20 = rows.iloc[-20:]
    lo, hi = float(last20["low"].min()), float(last20["high"].max())
    assert c.drop_ret == pytest.approx(ret(t), abs=1e-12)
    assert c.drop_z == pytest.approx((ret(t) - sect_mean) / sigma20, rel=1e-9)
    assert c.range_pos20 == pytest.approx((float(rows["close"].iloc[-1]) - lo) / (hi - lo), abs=1e-9)
    assert c.adv_rank == int(mem.loc[mem["ticker"] == t, "adv_rank"].iloc[0])
    assert c.signal_date == d and c.entry_date == e


def test_non_fundamental_negative_news_is_NF_and_qualifies(frames, sessions):
    d0 = sessions[IDX]
    fr, t, d, e = _event(frames, sessions, [(utc(d0, 11), "negative", "analyst_rating", "non_fundamental")])
    c = _find(_scan(fr, d), t)
    assert c is not None and c.bucket == "NF" and c.news_item_ids == ("evt-0",)
    dec = _decide(fr, e)
    assert t in [x.ticker for x in dec.candidates]


@pytest.mark.parametrize("extra", [("negative", "product", "fundamental"),
                                   ("neutral", "earnings", "non_fundamental")])
def test_fundamental_or_earnings_news_makes_F(frames, sessions, extra):
    d0 = sessions[IDX]
    fr, t, d, e = _event(frames, sessions, [(utc(d0, 11), "negative", "analyst_rating", "non_fundamental"),
                                            (utc(d0, 12), *extra)])
    assert _find(_scan(fr, d), t) is None, "F must not trade under H1"
    c = _find(_scan(fr, d, forced_params()), t)
    assert c is not None and c.bucket == "F"


def test_unclear_only_is_OTHER(frames, sessions):
    d0 = sessions[IDX]
    fr, t, d, e = _event(frames, sessions, [(utc(d0, 11), "negative", "commentary", "unclear")])
    c = _find(_scan(fr, d, forced_params()), t)
    assert c is not None and c.bucket == "OTHER"


def test_news_window_boundaries(frames, sessions):
    d, prev = sessions[IDX], sessions[IDX - 1]
    start = config.news_window_start(prev)
    # exactly at the window start: excluded -> no news -> NN
    fr, t, *_ = _event(frames, sessions, [(start, "negative", "analyst_rating", "non_fundamental")])
    assert _find(_scan(fr, d, forced_params()), t).bucket == "NN"
    # one minute after the start: included
    fr, t, *_ = _event(frames, sessions, [(start + timedelta(minutes=1), "negative", "analyst_rating", "non_fundamental")])
    assert _find(_scan(fr, d, forced_params()), t).bucket == "NF"
    # exactly at scan time: included
    fr, t, *_ = _event(frames, sessions, [(config.scan_time(d), "negative", "analyst_rating", "non_fundamental")])
    assert _find(_scan(fr, d, forced_params()), t).bucket == "NF"
    # one minute after scan time: not in the scan's window
    fr, t, *_ = _event(frames, sessions, [(config.scan_time(d) + timedelta(minutes=1), "negative", "analyst_rating", "non_fundamental")])
    assert _find(_scan(fr, d, forced_params()), t).bucket == "NN"


def test_overnight_veto(frames, sessions):
    d0, e0 = sessions[IDX], sessions[IDX + 1]
    nf = (utc(d0, 11), "negative", "analyst_rating", "non_fundamental")
    overnight = (utc(d0, 20), "negative", "legal_regulatory", "fundamental")
    fr, t, d, e = _event(frames, sessions, [nf, overnight])
    assert _find(_scan(fr, d), t) is not None, "the scan cannot see overnight news"
    dec = _decide(fr, e)
    assert t not in [c.ticker for c in dec.candidates], "fundamental overnight news must veto"
    types = require("swing.strategy.types")
    no_veto = _decide(fr, e, types.StrategyParams(overnight_veto=False))
    assert t in [c.ticker for c in no_veto.candidates]
    # News after the decision time cannot veto.
    late = (config.decision_time(e0) + timedelta(minutes=1), "negative", "legal_regulatory", "fundamental")
    fr2, t2, d2, e2 = _event(frames, sessions, [nf, late])
    assert t2 in [c.ticker for c in _decide(fr2, e2).candidates]


def test_ordering_and_picks(frames, sessions):
    d0 = sessions[IDX]
    fr, t, d, e = _event(frames, sessions, [(utc(d0, 11), "negative", "analyst_rating", "non_fundamental")])
    dec = _decide(fr, e, forced_params())
    zs = [(c.drop_z, c.ticker) for c in dec.candidates]
    assert zs == sorted(zs)
    assert len(dec.candidates) <= config.MAX_CANDIDATES
    assert list(dec.picks) == list(dec.candidates[: len(dec.picks)])
    assert len(dec.picks) == min(forced_params().max_picks, len(dec.candidates))
    for c in dec.candidates:
        assert c.drop_z <= forced_params().z_max and c.drop_ret <= forced_params().ret_max
