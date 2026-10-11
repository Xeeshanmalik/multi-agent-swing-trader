# Roadmap

## Phase 1: build on synthetic data (no API keys needed)
- market-data: `swing/asof.py`, `swing/data/universe.py`; tests in tests/leakage/test_asof.py and test_universe.py pass.
- news-intel: `swing/news/anonymize.py`, `swing/news/classify.py` with stubs; test_news_hygiene.py passes.
- quant: types, scan, decide, run_backtest, evaluator; all of tests/leakage passes, including `-m slow`.
- auditor: tests the frozen tests with planted bugs (docs/audits/frozen-suite.md); reviews each step.
- **Done when:** `make test` passes strict, auditor PASS.

## Phase 2: real data (needs MASSIVE_API_KEY in .env)
- market-data: survivorship-free daily history 2015-2026, reference data, parquet source; docs/gates/gate0-data.md.
- news-intel: historical news from the chosen source with the first-seen rule; docs/gates/gate0-news.md.
- Both: live collectors (prices after the close, news continuously) start recording real first-seen times.
- **Done when:** Gate 0 reports exist, auditor PASS, owner decision 1 made.

## Phase 3: labels (needs ANTHROPIC_API_KEY and owner approval)
- news-intel: frozen prompt, hand-made test headlines, cost estimate, then batch labeling after approval.
- auditor: hindsight check (anonymized vs original text on a sample).
- **Done when:** every in-window news item has a label; PROMPT_HASH and model_id reported.

## Phase 4: one pre-registered trial
- quant: Gate 1 counts (label-free), Gate 3 dry run on synthetic data.
- auditor: pre-trial audit.
- Owner signs docs/PREREGISTRATION.md, runs `make freeze`, tags, and gives the go.
- quant: H1 once, then diagnostics D1-D3; result in ledger/LEDGER.md.

## Phase 5 (only if H1 passes): lockbox, then paper trading
- Owner opens the lockbox for one confirmation run.
- If it passes: daily post-market scan and pre-market decision on paper for 3+ months.

## Owner decisions (the lead asks; nobody else decides)
1. Gate 0: news source and `DEV_START` (coverage-based, before any labels).
2. Labeling model, prompt and budget.
3. Gate 1: drop thresholds, once, only if fewer than 150 NF trades expected.
4. Sign the pre-registration and give the go for the trial.
5. Open the lockbox (once).
6. Any change to a frozen file, any extra spending.
