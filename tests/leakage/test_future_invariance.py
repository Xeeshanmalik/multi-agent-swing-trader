"""FROZEN. Scrambling anything that arrives after the cutoff must change nothing."""
import pytest

from swing import config
from tests.conftest import (assert_decisions_equal, assert_scans_equal, build_source,
                            forced_params, perturb_future, require)

IDXS = [300, 360]


def _decide(fr, e, params):
    return require("swing.strategy.signals").decide(build_source(fr), e, params)


def _scan(fr, d, params):
    return require("swing.strategy.signals").scan(build_source(fr), d, params)


def test_deterministic(frames, sessions):
    e = sessions[IDXS[0]]
    assert_decisions_equal(_decide(frames, e, forced_params()), _decide(frames, e, forced_params()))


@pytest.mark.parametrize("idx", IDXS)
@pytest.mark.parametrize("seed", [1, 2])
def test_decision_ignores_future(frames, sessions, idx, seed):
    e = sessions[idx]
    base = _decide(frames, e, forced_params())
    assert len(base.candidates) > 0, "test would be vacuous"
    scrambled = _decide(perturb_future(frames, config.decision_time(e), seed), e, forced_params())
    assert_decisions_equal(base, scrambled)


@pytest.mark.parametrize("seed", [3, 4])
def test_scan_ignores_future(frames, sessions, seed):
    d = sessions[IDXS[1]]
    base = _scan(frames, d, forced_params())
    assert len(base.candidates) > 0, "test would be vacuous"
    assert_scans_equal(base, _scan(perturb_future(frames, config.scan_time(d), seed), d, forced_params()))


def test_default_params_ignore_future(frames, sessions):
    types = require("swing.strategy.types")
    e = sessions[IDXS[1]]
    base = _decide(frames, e, types.StrategyParams())
    assert_decisions_equal(base, _decide(perturb_future(frames, config.decision_time(e), 9), e,
                                         types.StrategyParams()))
