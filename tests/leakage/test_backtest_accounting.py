"""FROZEN. Backtest P&L must use real prices, full costs, the benchmark, and never drop a delisting."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from swing import config
from tests.conftest import (assert_decisions_equal, build_source, copy_frames, forced_params,
                            require)

TRADE_COLS = ["signal_date", "entry_date", "exit_date", "ticker", "bucket", "adv_rank",
              "entry_price", "exit_price", "gross_return", "cost", "net_return",
              "bench_return", "excess_return", "exit_reason"]
METRICS = {"n_entry_days", "n_trades", "n_delisted_exits", "mean_net", "hit_rate_net",
           "mean_excess", "hit_rate_excess", "t_excess_nw", "sharpe_excess_annual",
           "max_drawdown_net", "n_trials_logged"}


@pytest.fixture(scope="module")
def delist_case(frames):
    """A ticker that crashes on d and is delisted after trading on the entry date."""
    fr = copy_frames(frames)
    sessions = sorted(fr["prices"]["date"].unique())
    ref = fr["reference"]
    p = fr["prices"]
    for t, last in zip(ref["ticker"], ref["delist_date"]):
        if last is None or pd.isna(last):
            continue
        L = sessions.index(pd.Timestamp(last).date())
        if L - 1 >= config.MIN_HISTORY + 30:
            break
    d, e = sessions[L - 1], sessions[L]
    rows = p[p["ticker"] == t].sort_values("date")
    prev_close = float(rows[rows["date"] < d]["close"].iloc[-1])
    m = (p["ticker"] == t) & (p["date"] == d)
    new_close = prev_close * 0.80
    p.loc[m, "close"] = new_close
    p.loc[m, "low"] = min(float(p.loc[m, "open"].iloc[0]), new_close) * 0.995
    assert new_close > config.MIN_PRICE
    return fr, t, d, e, sessions


def _run(fr, start, end, params=None):
    signals = require("swing.strategy.signals")
    return signals.run_backtest(build_source(fr), start, end, params or forced_params())


@pytest.fixture(scope="module")
def result(delist_case):
    fr, t, d, e, sessions = delist_case
    i = sessions.index(e)
    return _run(fr, sessions[i - 20], sessions[i + 15])


def test_trade_table_and_metrics(result):
    assert list(result.trades.columns[: len(TRADE_COLS)]) == TRADE_COLS
    assert METRICS <= set(result.metrics)
    assert result.metrics["n_trades"] == len(result.trades) > 10
    assert isinstance(result.config_hash, str) and result.config_hash


def test_delisting_is_not_dropped(result, delist_case):
    fr, t, d, e, sessions = delist_case
    row = result.trades[(result.trades["ticker"] == t)
                        & (pd.to_datetime(result.trades["entry_date"]).dt.date == e)]
    assert len(row) == 1, "a pick that delists during the hold must stay in the trade table"
    r = row.iloc[0]
    bar = fr["prices"].set_index(["ticker", "date"]).loc[(t, e)]
    assert r["exit_reason"] == "delisted"
    assert pd.Timestamp(r["exit_date"]).date() == e
    assert r["exit_price"] == pytest.approx(bar["close"], rel=1e-12)
    assert result.metrics["n_delisted_exits"] >= 1


def test_prices_costs_dates(result, delist_case):
    fr, t, d, e, sessions = delist_case
    px = fr["prices"].set_index(["ticker", "date"])
    end = max(pd.Timestamp(x).date() for x in result.trades["exit_date"])
    for r in result.trades.itertuples():
        sd, ed, xd = (pd.Timestamp(r.signal_date).date(), pd.Timestamp(r.entry_date).date(),
                      pd.Timestamp(r.exit_date).date())
        assert sessions.index(ed) == sessions.index(sd) + 1
        if r.exit_reason == "time":
            assert sessions.index(xd) == sessions.index(ed) + forced_params().hold_sessions - 1
        assert r.entry_price == pytest.approx(px.loc[(r.ticker, ed), "open"], rel=1e-12)
        assert r.exit_price == pytest.approx(px.loc[(r.ticker, xd), "close"], rel=1e-12)
        assert r.gross_return == pytest.approx(r.exit_price / r.entry_price - 1, abs=1e-12)
        assert r.cost == pytest.approx(config.round_trip_cost(int(r.adv_rank)) * config.COST_STRESS, abs=1e-15)
        assert r.net_return == pytest.approx(r.gross_return - r.cost, abs=1e-12)
        assert r.excess_return == pytest.approx(r.net_return - r.bench_return, abs=1e-12)


def test_benchmark_is_equal_weight_universe(result, delist_case):
    fr, t, d, e, sessions = delist_case
    asof = require("swing.asof")
    universe = require("swing.data.universe")
    src = build_source(fr)
    px = fr["prices"].set_index(["ticker", "date"])
    checked = 0
    for r in result.trades.drop_duplicates("entry_date").head(6).itertuples():
        sd, ed = pd.Timestamp(r.signal_date).date(), pd.Timestamp(r.entry_date).date()
        xd = sessions[sessions.index(ed) + forced_params().hold_sessions - 1]
        mem = universe.members(asof.AsOfView(src, config.scan_time(sd)), sd)
        rets = [px.loc[(tk, xd), "close"] / px.loc[(tk, ed), "open"] - 1
                for tk in mem["ticker"] if (tk, ed) in px.index and (tk, xd) in px.index]
        assert r.bench_return == pytest.approx(float(np.mean(rets)), abs=1e-12)
        checked += 1
    assert checked >= 3


def test_backtest_decisions_match_live_decide(result, delist_case):
    fr, *_ = delist_case
    signals = require("swing.strategy.signals")
    src = build_source(fr)
    assert len(result.decisions) == result.metrics["n_entry_days"]
    for dec in (result.decisions[3], result.decisions[-2]):
        assert dec.as_of == config.decision_time(dec.entry_date)
        assert_decisions_equal(dec, signals.decide(src, dec.entry_date, forced_params()))


def test_trades_are_the_picks(result, delist_case):
    fr = delist_case[0]
    traded_bars = set(zip(fr["prices"]["ticker"], fr["prices"]["date"]))
    picks = {(c.ticker, dec.entry_date) for dec in result.decisions for c in dec.picks
             if (c.ticker, dec.entry_date) in traded_bars}
    rows = {(r.ticker, pd.Timestamp(r.entry_date).date()) for r in result.trades.itertuples()}
    assert rows == picks


def test_no_exit_after_end(delist_case):
    fr, t, d, e, sessions = delist_case
    i = sessions.index(e)
    res = _run(fr, sessions[i - 6], sessions[i + 4])
    assert all(pd.Timestamp(x).date() <= sessions[i + 4] for x in res.trades["exit_date"])
    assert max(pd.Timestamp(x).date() for x in res.trades["entry_date"]) <= sessions[i + 3]


def test_every_backtest_is_logged(delist_case):
    fr, t, d, e, sessions = delist_case
    i = sessions.index(e)
    r1 = _run(fr, sessions[i - 4], sessions[i])
    r2 = _run(fr, sessions[i - 4], sessions[i])
    with open(os.environ["SWING_TRIALS_LOG"]) as fh:
        lines = [json.loads(x) for x in fh if x.strip()]
    assert len(lines) == 2
    assert r1.metrics["n_trials_logged"] == 1 and r2.metrics["n_trials_logged"] == 2
    assert lines[0]["config_hash"] == r1.config_hash
