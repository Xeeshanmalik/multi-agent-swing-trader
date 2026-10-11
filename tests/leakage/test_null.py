"""FROZEN. On pure noise an honest system cannot show a strong edge.

A strong 'edge' on random walks with random news labels almost always means
lookahead, a cost bug, or a benchmark bug.
"""
import numpy as np
import pytest

from tests.conftest import build_source, forced_params, make_frames, require


@pytest.mark.slow
@pytest.mark.parametrize("seed", [11, 12])
def test_no_edge_on_noise(seed):
    signals = require("swing.strategy.signals")
    fr = make_frames(seed=seed, n_tickers=50, n_days=560, start="2019-01-02")
    sessions = sorted(fr["prices"]["date"].unique())
    res = signals.run_backtest(build_source(fr), sessions[270], sessions[-1], forced_params())
    ex = res.trades["excess_return"].to_numpy(dtype=float)
    assert len(ex) >= 300, "forced params must trade nearly every day"
    hit = float((ex > 0).mean())
    t = ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex)))
    assert hit < 0.60, f"excess hit rate {hit:.1%} on noise: suspect lookahead"
    assert t < 3.0, f"excess t {t:.2f} on noise: suspect lookahead"
    assert res.metrics["t_excess_nw"] < 3.0
