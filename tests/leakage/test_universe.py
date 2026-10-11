"""FROZEN. The universe must be point-in-time and survivorship-free."""
import pandas as pd

from swing import config
from tests.conftest import build_source, perturb_future, require


def _members(frames_, d):
    asof = require("swing.asof")
    universe = require("swing.data.universe")
    v = asof.AsOfView(build_source(frames_), config.scan_time(d))
    return universe.members(v, d)


def test_shape_and_ranking(frames, sessions):
    m = _members(frames, sessions[300])
    assert list(m.columns[:3]) == ["ticker", "adv_rank", "sector"]
    assert list(m["adv_rank"]) == list(range(1, len(m) + 1))
    assert len(m) <= config.UNIVERSE_TOP_N and len(m) > 20


def test_rules_price_history_and_bar_on_date(frames, sessions):
    d = sessions[300]
    m = set(_members(frames, d)["ticker"])
    p = frames["prices"]
    low = p[(p["date"] == d) & (p["close"] < config.MIN_PRICE)]["ticker"]
    assert len(low) > 0 and not set(low) & m, "names under MIN_PRICE must be excluded"
    early = _members(frames, sessions[config.MIN_HISTORY - 10])
    assert len(early) == 0, "no name has MIN_HISTORY sessions yet"
    traded_today = set(p[p["date"] == d]["ticker"])
    assert m <= traded_today


def test_later_delisted_names_are_included_before_delisting(frames, sessions):
    ref = frames["reference"]
    delisted = ref[ref["delist_date"].notna()]
    hits = 0
    for t, last in zip(delisted["ticker"], delisted["delist_date"]):
        last = pd.Timestamp(last).date()
        idx = sessions.index(last)
        if idx - 3 >= config.MIN_HISTORY + 5:
            d = sessions[idx - 3]
            assert t in set(_members(frames, d)["ticker"]), f"{t} traded on {d} but was dropped"
            hits += 1
    assert hits >= 1


def test_universe_ignores_the_future(frames, sessions):
    d = sessions[320]
    base = _members(frames, d)
    scrambled = _members(perturb_future(frames, config.scan_time(d), seed=3), d)
    pd.testing.assert_frame_equal(base.reset_index(drop=True), scrambled.reset_index(drop=True))
