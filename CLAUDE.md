# multi-agent-swing-trader

Research tool. Goal: find out, honestly, whether hypothesis H1 in
docs/PREREGISTRATION.md (buy liquid US stocks that fell sharply on negative but
non-fundamental news; sell two sessions later) beats an equal-weight benchmark
after costs. "No edge" is a valid, valuable answer. No order placement and no
broker credentials, ever.

## Team (one lead, four teammates)

| Name | Owns (may edit) | Job |
|---|---|---|
| lead | docs/STATUS.md, docs/ROADMAP.md | Coordinates, delegates, reports to the owner. Writes no code. |
| market-data | swing/asof.py, swing/data/, scripts/data/, tests/data/, docs/gates/gate0-data.md | Survivorship-free prices, reference data, universe, live collector |
| news-intel | swing/news/, scripts/news/, tests/news/, docs/gates/gate0-news.md | News ingestion, first-seen timestamps, anonymized LLM labels |
| quant | swing/strategy/, swing/cli.py, swing/research/, tests/strategy/, ledger/, docs/gates/gate1-*, docs/gates/gate3-* | H1 rule, backtest, evaluation, trial ledger |
| auditor | tests/audit/, docs/audits/ | Independent red team. Reads everything, edits only its own folders. |

Nobody edits another agent's files. Ask the owner of the file by message.

## Frozen: never edit, never work around

contracts/, swing/config.py, swing/env.py, docs/PREREGISTRATION.md,
tests/conftest.py, tests/leakage/, tests/test_frozen.py, Makefile,
scripts/start-team.sh, scripts/audit.py, .claude/, FROZEN.sha256.
A hook blocks edits to these paths. If a frozen file looks wrong, send the
lead the evidence; only the owner changes them.
Never weaken, skip or delete a test to make it pass.

## Rules that protect the result

- Read data only through `swing.asof.AsOfView`. No code path may see data
  after its `as_of`.
- Development window only (config.DEV_START..DEV_END). Never touch the lockbox
  or flip `LOCKBOX_OPEN`.
- Every backtest is a trial and is logged in ledger/trials.jsonl. Never edit or
  delete ledger lines. Run real-data backtests only when the lead says the
  owner approved that exact trial.
- Results that look too good (excess hit rate > 60%, t > 4, Sharpe > 3) mean
  "find the leak" before anything else.
- Secrets: code gets them with `swing.env.require_env("NAME")`. Never read,
  print, log or commit .env or a key.
- Spending money (bulk LLM labeling, paid data pulls beyond the plan) needs
  the owner's approval through the lead, with a cost estimate first.

## Working style

- Small steps; run `make test-fast` after each; commit with a clear message.
  Never push, rebase or reset.
- Messages to other agents: short, concrete, with file paths and test names.
- When blocked, say exactly what you need and from whom, then stop. Don't spin.
- "Done" means `make test` passes. Don't report done without running it.

## Commands

    make test-fast   fast tests (also run automatically when a teammate goes idle)
    make test        full suite, strict: missing modules fail instead of skip
    make audit       frozen files and the trial ledger are intact since the last tag
    make freeze      owner only: record checksums of frozen files
