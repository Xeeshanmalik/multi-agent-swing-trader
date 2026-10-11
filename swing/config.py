"""FROZEN after the owner signs docs/PREREGISTRATION.md. Only the owner edits this file.

Every rule that decides what a backtest *means* lives here: clock times, the
universe, costs, the hold, and which dates are off-limits. Agents read it;
they never change it. See contracts/strategy.md.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------ clock
MARKET_TZ = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)
BAR_DELAY_MIN = 15            # a daily bar is usable 15 min after the close
SCAN_TIME = time(16, 30)      # post-market scan on the signal date
DECISION_TIME = time(9, 0)    # pre-market confirmation on the entry date
NEWS_WINDOW_START = time(16, 0)  # news window opens at 16:00 ET the session before the signal date

# --------------------------------------------------------------- universe
UNIVERSE_TOP_N = 1000         # most liquid names by median dollar volume
ADV_LOOKBACK = 60             # sessions used for that median (bars <= signal date)
MIN_HISTORY = 250             # sessions of history before a name can qualify
MIN_PRICE = 5.0

# ---------------------------------------------------------------- trading
HOLD_SESSIONS = 2             # buy at the entry-date open, sell at the close one session later
MAX_PICKS_PER_DAY = 2
MAX_CANDIDATES = 20


def round_trip_cost(adv_rank: int) -> float:
    """Round-trip cost (decimal return) by liquidity rank: 1 = most liquid."""
    if adv_rank <= 300:
        return 0.0010          # 10 bp
    if adv_rank <= 600:
        return 0.0020          # 20 bp
    return 0.0030              # 30 bp


COST_STRESS = 1.0             # the owner sets 2.0 for the stress run

# ---------------------------------------------------------------- windows
# Development: the only period agents may evaluate on. The owner may move
# DEV_START once, at Gate 0, based on news coverage, before any label is seen.
DEV_START = date(2017, 1, 3)
DEV_END = date(2022, 12, 30)
# Lockbox: one confirmation run of one frozen spec, by the owner. After it is
# opened it stays open, which also enables live paper trading.
LOCKBOX_START = date(2023, 1, 3)
LOCKBOX_END = date(2026, 9, 30)
LOCKBOX_OPEN = False

RANDOM_SEED = 42


class SealedPeriodError(RuntimeError):
    """Raised when code tries to see data the protocol has not released."""


# ---------------------------------------------------------------- helpers
def assert_aware(ts: datetime) -> None:
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"timezone-aware datetime required, got {ts!r}")


def _utc(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=MARKET_TZ).astimezone(timezone.utc)


def bar_available_at(session: date) -> datetime:
    close = datetime.combine(session, SESSION_CLOSE, tzinfo=MARKET_TZ)
    return (close + timedelta(minutes=BAR_DELAY_MIN)).astimezone(timezone.utc)


def scan_time(signal_date: date) -> datetime:
    """Information cutoff (UTC) for the post-market scan on the signal date."""
    return _utc(signal_date, SCAN_TIME)


def decision_time(entry_date: date) -> datetime:
    """Information cutoff (UTC) for the pre-market decision on the entry date."""
    return _utc(entry_date, DECISION_TIME)


def news_window_start(prev_session: date) -> datetime:
    """Start (UTC, exclusive) of the news window for a signal date: 16:00 ET on the previous session."""
    return _utc(prev_session, NEWS_WINDOW_START)


def last_allowed_date() -> date | None:
    """Latest date any as_of may fall on. None means unrestricted (lockbox opened)."""
    return None if LOCKBOX_OPEN else DEV_END


def assert_released(as_of: datetime) -> None:
    """Every data view, scan and decision calls this first."""
    assert_aware(as_of)
    last = last_allowed_date()
    if last is not None and as_of.astimezone(MARKET_TZ).date() > last:
        raise SealedPeriodError(
            f"as_of {as_of.isoformat()} is after {last}: the lockbox is closed. "
            "Only the owner opens it, once."
        )


def assert_range_released(start: date, end: date) -> None:
    """Backtests call this before doing any work."""
    last = last_allowed_date()
    if last is not None and end > last:
        raise SealedPeriodError(f"range {start}..{end} runs past {last}: the lockbox is closed.")
