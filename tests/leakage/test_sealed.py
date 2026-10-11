"""FROZEN. Nothing may look past the development window until the owner opens the lockbox."""
from datetime import date, timedelta

import pytest

from swing import config

pytestmark = pytest.mark.skipif(config.LOCKBOX_OPEN, reason="lockbox opened by the owner")


def test_decide_refuses_lockbox(source, signals):
    with pytest.raises(config.SealedPeriodError):
        signals.decide(source, config.LOCKBOX_START + timedelta(days=7))


def test_scan_refuses_lockbox(source, signals):
    with pytest.raises(config.SealedPeriodError):
        signals.scan(source, config.LOCKBOX_START + timedelta(days=7))


def test_backtest_refuses_overlap(source, signals):
    with pytest.raises(config.SealedPeriodError):
        signals.run_backtest(source, date(2022, 6, 1), config.LOCKBOX_START + timedelta(days=3))


def test_live_dates_refused_while_closed(source, signals):
    with pytest.raises(config.SealedPeriodError):
        signals.decide(source, config.LOCKBOX_END + timedelta(days=12))
