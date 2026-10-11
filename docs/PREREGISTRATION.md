# Pre-registration: H1, news-driven overreaction reversal

Status: **DRAFT — not signed.** The owner reviews and edits this file, signs
the bottom, runs `make freeze`, and tags `prereg-h1`. After that it never
changes. Any change after signing is a new hypothesis with a new trial.

## 1. Hypothesis

When a liquid US stock falls sharply on a day when the only news about it is
negative but **non-fundamental** (a downgrade, sector or macro fear, a rumor,
commentary), the drop partly reverses over the next two sessions. When the
news is **fundamental** (earnings, guidance, regulation, litigation, product
failure, fraud), it does not.

Why it might persist: liquidity provision. Forced and sentiment-driven
sellers push prices below value for a day or two, and the buyer is paid for
absorbing that. Why it might not: the effect is well known, large funds trade
it, and our previous trial of a similar weekly reversal (H-B, old project)
had t = 2.11, short of its bar.

## 2. Exact rule

As written in `contracts/strategy.md` "Rules for H1", with these values:

| Parameter | Value |
|---|---|
| Universe | top 1,000 US common stocks by 60-session median dollar volume, price >= $5, >= 250 sessions of history, survivorship-free |
| Drop | `drop_z <= -2.5` and `drop_ret <= -3%` on the signal date |
| Qualifying news | bucket `NF` only |
| Overnight veto | on |
| Picks | up to 2 per entry date, most negative `drop_z` first |
| Entry / exit | buy at the next session's open, sell at the following session's close (2 sessions) |
| Costs | 10 / 20 / 30 bp round trip by liquidity rank (1-300 / 301-600 / 601-1000) |
| Benchmark | equal-weight universe, same entry open and exit close |
| Labeler | `PROMPT_HASH` = ______, `model_id` = ______ (filled at Gate 2, before any trial) |

## 3. Data windows

- Development: `config.DEV_START` to `config.DEV_END` (2017-01-03 to 2022-12-30,
  start may move once at Gate 0).
- Lockbox: 2023-01-03 to 2026-09-30. Closed. Opened once by the owner, only if
  H1 passes on development data.
- After the lockbox: forward paper trading, which is the final out-of-sample test.

## 4. Gates before the one development run

- **Gate 0, data:** survivorship-free prices (delisted names present), news
  coverage by year and by liquidity tier, share of tickers with any news,
  vendor timestamp sanity. Label-free and return-free. The owner may move
  `DEV_START` once here.
- **Gate 1, counts:** label-free counts of qualifying days and trades per year
  and per bucket (`NF`, `F`, `NN`), computed with return columns removed. If
  fewer than 150 `NF` trades are expected, the owner may change the two drop
  thresholds once, here, before any return is seen. Record the change.
- **Gate 2, leakage:** `make test` strict, including the frozen leakage suite
  and the auditor's tests for this rule; labeler frozen and its hash recorded above.
- **Gate 3, dry run:** the exact command on synthetic data; it must be rejected
  on noise and write only to a temporary trial log.

## 5. Pass criterion (development run, evaluated by a script committed before the run)

1. At least 150 trades.
2. Mean excess > 0 with `t_excess_nw >= 2.5` (higher than the old 2.4 because
   this family has been tried before).
3. Mean excess > 0 in at least 4 of the 6 years.
4. Excluding 2020: mean excess > 0 with t >= 2.0.
5. Robustness: with the best 1% of trades removed, mean excess is still > 0.
6. Calibration at the pick: |mean `prob_beat_bench` − realized share beating the
   benchmark| <= 0.05.
7. Cost stress: mean excess still > 0 with `COST_STRESS = 2.0`.

Leak red flags (stop and hunt before reporting anything): `t_excess_nw >= 4`,
`hit_rate_excess > 0.60`, `sharpe_excess_annual > 3`.

## 6. Diagnostics (declared now, reported with the result, never used to pick a winner)

Each is logged as a trial in the ledger.

- D1: the same rule with `buckets = ("F",)`. The hypothesis predicts a lower,
  likely negative, mean excess than H1.
- D2: the same rule with `buckets = ("NN",)` (no news at all).
- D3: H1 trades split by `range_pos20 <= 0.10` versus `> 0.10`, testing the
  owner's "near the bottom of its range" intuition. Reported only.

## 7. Lockbox confirmation (only if section 5 passes)

One run of the identical spec on 2023-01-03 to 2026-09-30, by the owner.
Pass: at least 60 trades, mean excess > 0, `t_excess_nw >= 1.65`, and
calibration within 0.05. No re-run, no re-tuning, whatever the result.

## 8. Paper trading and kill rules (only if section 7 passes)

- Daily post-market scan and pre-market decision, logged before the open.
- At least 3 months or 60 trades before any real money.
- Stop if the paper mean excess after 60 trades is below zero, or if realized
  calibration drifts more than 0.08 from predicted.
- First real money: small fixed size per trade, never more than 2 open
  positions, no leverage.

## 9. Multiple-testing accounting

The ledger counts every run: H1, D1, D2, D3, the lockbox run, and the old
project's 6 trials plus 2 label looks. The Deflated Sharpe Ratio in the result
report uses that total.

---

Signed by the owner: ________________  Date: ____________
