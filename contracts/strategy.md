# Contract: strategy, decisions and backtest (FROZEN)

Owner: `quant`. Implements hypothesis H1 in `docs/PREREGISTRATION.md`.
Reads data only through `AsOfView` (see `contracts/data.md`). Returns are
decimals (`0.004` = 0.4%).

## Calendar and timing

- The session calendar is the sorted set of dates present in `prices`.
- **Signal date** `d`: the session on which the drop happens.
- **Entry date** `e`: the next session after `d`. Buy at `open(e)`.
- **Exit date** `x`: `HOLD_SESSIONS - 1` sessions after `e`. Sell at `close(x)`.
  With `HOLD_SESSIONS = 2`, that's buy Tuesday's open, sell Wednesday's close.
- **Post-market scan** on `d` uses `as_of = config.scan_time(d)` (16:30 ET).
- **Pre-market decision** on `e` uses `as_of = config.decision_time(e)` (09:00 ET).
  The signal date is the last session whose bar is visible at that time.

## Types (`swing/strategy/types.py`)

```python
@dataclass(frozen=True)
class StrategyParams:            # defaults = the pre-registered H1 spec
    z_max: float = -2.5          # qualify if drop_z <= z_max
    ret_max: float = -0.03       # and drop_ret <= ret_max
    buckets: tuple[str, ...] = ("NF",)   # news buckets that may trade
    max_picks: int = 2           # == config.MAX_PICKS_PER_DAY for registered trials
    hold_sessions: int = 2       # == config.HOLD_SESSIONS for registered trials
    overnight_veto: bool = True

@dataclass(frozen=True)
class Candidate:
    ticker: str
    signal_date: date
    entry_date: date
    drop_ret: float              # close(d) / previous close - 1
    drop_z: float                # (drop_ret - sector mean drop_ret) / sigma20
    bucket: str                  # "NF", "F", "NN" or "OTHER"
    news_item_ids: tuple[str, ...]
    range_pos20: float           # (close(d) - 20-session low) / (20-session high - low), in [0, 1]
    adv_rank: int
    prob_beat_bench: float       # in [0, 1]
    exp_excess: float
    interval_80: tuple[float, float]   # lo <= hi
    drivers: tuple[str, ...]     # <= 5 short reasons, written for a human

@dataclass(frozen=True)
class ScanResult:
    signal_date: date
    as_of: datetime              # == config.scan_time(signal_date)
    candidates: tuple[Candidate, ...]    # qualifying names, sorted by drop_z then ticker

@dataclass(frozen=True)
class Decision:
    entry_date: date
    as_of: datetime              # == config.decision_time(entry_date)
    picks: tuple[Candidate, ...] # <= params.max_picks, a prefix of the surviving candidates
    candidates: tuple[Candidate, ...]    # <= config.MAX_CANDIDATES, sorted by drop_z then ticker
    reason: str

@dataclass
class BacktestResult:
    trades: pd.DataFrame
    decisions: list[Decision]
    metrics: dict[str, float]
    config_hash: str
```

## Functions (`swing/strategy/signals.py`)

```python
def scan(source, signal_date: date, params: StrategyParams | None = None) -> ScanResult
def decide(source, entry_date: date, params: StrategyParams | None = None) -> Decision
def run_backtest(source, start: date, end: date, params: StrategyParams | None = None) -> BacktestResult
```

## Rules for H1 (exact)

1. **Universe:** `swing.data.universe.members(view, d)`.
2. **Drop:** `drop_ret` from the ticker's previous bar to `close(d)`;
   sector mean over universe members in the same sector; `sigma20` = sample
   standard deviation of the ticker's daily returns over the 20 sessions ending
   the session before `d`. Qualify if `drop_z <= z_max` and `drop_ret <= ret_max`.
3. **News window for d:** items tagged with the ticker whose `first_seen_at` is
   after `config.news_window_start(previous session)` and at or before
   `config.scan_time(d)`.
4. **Bucket**, from that window's labels:
   - `F` if any label has `persistence == "fundamental"` or `category == "earnings"`;
   - else `NF` if at least one label has `sentiment == "negative"` and
     `persistence == "non_fundamental"`;
   - else `NN` if the window has no items at all;
   - else `OTHER` (never trades).
5. **Overnight veto** (decide only): drop a candidate if any item for it first
   seen after `scan_time(d)` and at or before `decision_time(e)` has a label with
   `persistence == "fundamental"` or `category == "earnings"`.
6. **Picks:** surviving candidates in order, first `max_picks`. The probability
   estimate never changes which names are picked.
7. **Probability estimate:** walk-forward only, from past H1 trades whose exit
   bar is visible at `as_of`, shrunk toward the universe base rate. With fewer
   than 30 past trades use `prob_beat_bench = 0.5`, `exp_excess = 0.0`.

## Backtest accounting (exact)

- `run_backtest` calls `config.assert_range_released(start, end)` before any
  work. It reads raw prices only for P&L; every decision comes from `decide`.
- Entry dates are sessions in `[start, end]` whose exit date is also `<= end`.
- One row per entered pick in `trades`, with columns:
  `signal_date, entry_date, exit_date, ticker, bucket, adv_rank, entry_price,
  exit_price, gross_return, cost, net_return, bench_return, excess_return,
  exit_reason`.
- `entry_price = open(e)`; `exit_price = close(x)`; `gross_return = exit / entry - 1`;
  `cost = config.round_trip_cost(adv_rank) * config.COST_STRESS`;
  `net_return = gross_return - cost`.
- **Delisting or missing bar during the hold:** exit at the ticker's last close
  in `[e, x]`, `exit_reason = "delisted"`, and `exit_date` is the date of that
  close. The trade is never dropped.
  Otherwise `exit_reason = "time"`. If the ticker has no bar on `e`, the pick
  is skipped and the decision's reason says so.
- `bench_return`: equal-weight mean of `close(x) / open(e) - 1` over universe
  members on `d` that have bars on both `e` and `x`. No cost.
  `excess_return = net_return - bench_return`.
- `metrics` must include: `n_entry_days, n_trades, n_delisted_exits,
  mean_net, hit_rate_net, mean_excess, hit_rate_excess, t_excess_nw,
  sharpe_excess_annual, max_drawdown_net, n_trials_logged`.
  `t_excess_nw` uses Newey-West with lag `hold_sessions`.
- **Trial log:** every `run_backtest` call appends one JSON line
  (`timestamp, config_hash, params, start, end, metrics`) to the file named by
  env var `SWING_TRIALS_LOG` (default `ledger/trials.jsonl`) and sets
  `metrics["n_trials_logged"]` to the line count after appending. Never edit
  or delete lines. `make audit` checks this against git.
- Same inputs give identical outputs (fixed seeds, stable sorts).

## CLI (`swing/cli.py`)

```
python -m swing.cli backtest --start YYYY-MM-DD --end YYYY-MM-DD
python -m swing.cli scan --date YYYY-MM-DD        # post-market candidates
python -m swing.cli decide --date YYYY-MM-DD      # pre-market picks
```

`backtest` writes a report directory under `data/derived/reports/` with
`trades.parquet`, `metrics.json`, a by-year table and a calibration table.
