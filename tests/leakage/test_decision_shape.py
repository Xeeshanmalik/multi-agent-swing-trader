"""FROZEN. Decisions must have the shape the daily report and the backtest rely on."""
from swing import config
from tests.conftest import forced_params, require


def test_decision_shape(source, signals, sessions):
    e = sessions[340]
    dec = signals.decide(source, e, forced_params())
    assert dec.entry_date == e and dec.as_of == config.decision_time(e)
    assert isinstance(dec.reason, str) and dec.reason
    assert len(dec.picks) <= forced_params().max_picks
    for c in dec.candidates:
        assert c.entry_date == e and c.signal_date == sessions[339]
        assert c.bucket in ("NF", "F", "NN", "OTHER")
        assert 0.0 <= c.prob_beat_bench <= 1.0
        lo, hi = c.interval_80
        assert lo <= hi
        assert 0.0 <= c.range_pos20 <= 1.0
        assert 1 <= c.adv_rank <= config.UNIVERSE_TOP_N
        assert len(c.drivers) <= 5 and all(isinstance(s, str) and s for s in c.drivers)


def test_scan_shape(source, signals, sessions):
    d = sessions[339]
    s = signals.scan(source, d, forced_params())
    assert s.signal_date == d and s.as_of == config.scan_time(d)
    keys = [(c.drop_z, c.ticker) for c in s.candidates]
    assert keys == sorted(keys)


def test_defaults_are_the_preregistered_spec():
    types = require("swing.strategy.types")
    p = types.StrategyParams()
    assert (p.z_max, p.ret_max, tuple(p.buckets), p.max_picks, p.hold_sessions, p.overnight_veto) == \
        (-2.5, -0.03, ("NF",), config.MAX_PICKS_PER_DAY, config.HOLD_SESSIONS, True)
