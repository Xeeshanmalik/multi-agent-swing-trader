# Contract: data layer (FROZEN)

Owners: `market-data` builds prices, reference data and the universe.
`news-intel` builds news and news labels. `quant` only reads, and only through
`AsOfView`. All timestamps are timezone-aware UTC. Naive datetimes raise
`ValueError`.

## Tables

**prices**: one row per ticker per session the ticker traded. Delisted names
are kept; their rows simply stop. Never drop a ticker because it no longer trades.

| column | type | notes |
|---|---|---|
| ticker | str | point-in-time symbol on that date |
| date | date | session date |
| open, high, low, close | float | split- and dividend-adjusted consistently |
| volume | float | shares |
| available_at | UTC timestamp | `config.bar_available_at(date)` |

**reference**: one row per ticker.

| column | type | notes |
|---|---|---|
| ticker | str | |
| company_names | tuple[str, ...] | every name the company traded under; used by the anonymizer |
| sector | str | 11 GICS-style sectors; static mapping (known limitation) |
| list_date | date | first session |
| delist_date | date or null | last session, null if still listed |

**news**: one row per article.

| column | type | notes |
|---|---|---|
| item_id | str | unique |
| tickers | tuple[str, ...] | companies the article is about |
| headline | str | |
| body | str | may be empty |
| source | str | publisher |
| published_at | UTC | what the vendor reports; NOT a visibility field |
| first_seen_at | UTC | the ONLY visibility field (rules below) |

**news_labels**: one row per (item, ticker), produced only by `swing.news.classify`.

| column | type | notes |
|---|---|---|
| item_id | str | |
| ticker | str | |
| sentiment | str | `negative`, `neutral`, `positive` |
| category | str | one of the 11 categories below |
| persistence | str | `fundamental`, `non_fundamental`, `unclear` |
| prompt_hash | str | hash of the frozen prompt template |
| model_id | str | exact model ID used |

Categories (frozen taxonomy; `CATEGORIES` in `swing/news/classify.py` must equal
this tuple, in this order): `earnings, guidance, analyst_rating,
legal_regulatory, product, management, mna, capital_markets, macro_sector,
commentary, other`.

A label is visible exactly when its news item is visible. It never has its own
availability time, because it is a pure function of the article text.

## Modules

| Module | Owner | Must provide |
|---|---|---|
| `swing/asof.py` | market-data | `InMemorySource(prices, reference, news=None, news_labels=None)`, `AsOfView(source, as_of)` with `.prices()`, `.reference()`, `.news()`, `.news_labels()` |
| `swing/data/universe.py` | market-data | `members(view, signal_date) -> pandas.DataFrame` with columns `ticker, adv_rank, sector`, sorted by `adv_rank` |
| `swing/news/anonymize.py` | news-intel | `anonymize(text, ticker, company_names) -> str` |
| `swing/news/classify.py` | news-intel | `PROMPT_TEMPLATE`, `PROMPT_HASH`, `CATEGORIES`, `classify_items(news, reference, client, model_id) -> news_labels DataFrame` |

`AsOfView(source, as_of)` calls `config.assert_released(as_of)` first, then
filters: prices by `available_at <= as_of`, news by `first_seen_at <= as_of`,
news_labels by joining to visible news. `reference()` is static.

`members(view, d)` uses only bars dated `<= d` that are visible in `view`:
names with `close(d) >= MIN_PRICE`, at least `MIN_HISTORY` sessions of history,
and a bar on `d`, ranked by median dollar volume over the last `ADV_LOOKBACK`
sessions; top `UNIVERSE_TOP_N`. Names that delist later must still appear on
dates when they traded.

## Point-in-time rules for real data

- **Survivorship.** Build the price history from per-date snapshots of all
  traded tickers (for Massive, the grouped daily aggregates endpoint or flat
  files), not from today's ticker list. Track ticker reuse and renames by a
  stable company ID (CIK or composite FIGI), not by symbol.
- **Live news.** The live collector writes `first_seen_at` = the time our
  system first stored the article.
- **Historical news.** We did not see it live, so use a conservative rule:
  `first_seen_at = published_at + 30 minutes`. Record the rule in a
  `provenance` column. Report the share of items whose vendor timestamp looks
  wrong (e.g. after the price reaction).
- **Raw files** go under `data/raw/` (git-ignored) as parquet and are never
  overwritten; derived tables go under `data/derived/`. Every download writes a
  manifest line: endpoint, parameters, row count, retrieval time.
- Secrets (API keys) live in `.env`, which no agent reads; code reads them from
  environment variables.

## LLM news labels: anti-hindsight rules

The labeling model was trained on data that may include what happened to these
stocks afterwards. To stop it from "remembering" outcomes:

1. The classifier sees only `anonymize(headline + body, ticker, company_names)`.
   The ticker, cashtags and every company name are replaced with `the company`.
   It never sees prices, returns, dates or the ticker.
2. The prompt template is frozen; `PROMPT_HASH` is stored on every label.
   Changing the prompt or model creates a new label set and counts as a new
   trial in the ledger.
3. Model output outside the allowed values is coerced, never passed through:
   sentiment to `neutral`, category to `other`, persistence to `unclear`.
4. Labels are deterministic (temperature 0) and cached: never re-label an item
   already labeled with the same `(prompt_hash, model_id)`.
5. Bulk historical labeling uses the Message Batches API with a small model;
   the exact model ID goes in `model_id`.
