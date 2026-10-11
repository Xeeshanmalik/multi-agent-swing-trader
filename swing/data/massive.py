"""Massive (formerly Polygon.io) REST client: polite, retrying, manifest-logging.

Nothing here runs at import time. The API key is fetched with
`swing.env.require_env("MASSIVE_API_KEY")` on the first request and is sent in
an Authorization header, so it never appears in URLs, manifests or logs.

Every successful download appends one line to data/raw/manifest.jsonl:
endpoint, params, rows, retrieved_at (UTC ISO), plus elapsed seconds and pages.
Raw bytes are saved by callers (`save_raw`) as parquet, never overwritten.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import pandas as pd

BASE_URL = "https://api.massive.com"
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.jsonl"

RETRY_STATUS = {429, 500, 502, 503, 504}


class MassiveError(RuntimeError):
    pass


class MassiveClient:
    def __init__(self, session=None, *, key_getter: Callable[[], str] | None = None,
                 min_interval: float = 0.25, max_retries: int = 5, backoff: float = 1.0,
                 timeout: float = 30.0, manifest_path: Path | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 base_url: str = BASE_URL):
        self._session = session
        self._key_getter = key_getter
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout
        self.manifest_path = Path(manifest_path) if manifest_path else MANIFEST
        self._sleep = sleep
        self._clock = clock
        self.base_url = base_url.rstrip("/")
        self._last = None

    # ------------------------------------------------------------ plumbing
    def _headers(self) -> dict:
        if self._key_getter is None:
            from swing.env import require_env
            key = require_env("MASSIVE_API_KEY")
        else:
            key = self._key_getter()
        return {"Authorization": f"Bearer {key}"}

    def _sess(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def get(self, url_or_path: str, params: dict | None = None) -> dict:
        url = url_or_path if url_or_path.startswith("http") else f"{self.base_url}{url_or_path}"
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                r = self._sess().get(url, params=params, headers=self._headers(),
                                     timeout=self.timeout)
            except Exception as e:                      # network error: retry
                if attempt >= self.max_retries:
                    raise MassiveError(f"GET failed after retries: {type(e).__name__}") from None
                self._sleep(self.backoff * 2 ** attempt)
                continue
            if r.status_code in RETRY_STATUS:
                if attempt >= self.max_retries:
                    raise MassiveError(f"HTTP {r.status_code} after {attempt + 1} attempts")
                ra = r.headers.get("Retry-After") if getattr(r, "headers", None) else None
                try:
                    delay = float(ra) if ra is not None else self.backoff * 2 ** attempt
                except ValueError:
                    delay = self.backoff * 2 ** attempt
                self._sleep(delay)
                continue
            if r.status_code != 200:
                raise MassiveError(f"HTTP {r.status_code} for {_strip(url)}")
            return r.json()
        raise MassiveError("unreachable")

    def _log(self, endpoint: str, params: dict, rows: int, pages: int, t0: float) -> None:
        line = {"endpoint": endpoint, "params": _clean(params), "rows": rows, "pages": pages,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_s": round(self._clock() - t0, 3)}
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "a") as f:
            f.write(json.dumps(line, sort_keys=True) + "\n")

    def paged(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Follow `next_url` until exhausted; return all `results`; write a manifest line."""
        params = dict(params or {})
        t0 = self._clock()
        out, pages, url, p = [], 0, endpoint, params
        while url:
            data = self.get(url, p)
            pages += 1
            out.extend(data.get("results") or [])
            url, p = data.get("next_url"), None        # next_url already carries its query
        self._log(endpoint, params, len(out), pages, t0)
        return out

    # ------------------------------------------------------------ endpoints
    def grouped_daily(self, day: date, adjusted: bool = False) -> pd.DataFrame:
        """All US stocks that traded on `day` (one row each). Unadjusted by default so the
        per-date snapshot is exactly what traded that day; adjust later from splits."""
        res = self.paged(f"/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}",
                         {"adjusted": str(adjusted).lower()})
        return parse_grouped(res, day)

    def tickers_on(self, day: date, active: bool | None = None) -> pd.DataFrame:
        params = {"market": "stocks", "date": day.isoformat(), "limit": 1000}
        if active is not None:
            params["active"] = str(active).lower()
        return pd.DataFrame(self.paged("/v3/reference/tickers", params))

    def ticker_details(self, ticker: str, day: date | None = None) -> dict:
        params = {"date": day.isoformat()} if day else {}
        t0 = self._clock()
        data = self.get(f"/v3/reference/tickers/{ticker}", params)
        self._log(f"/v3/reference/tickers/{ticker}", params, 1 if data.get("results") else 0, 1, t0)
        return data.get("results") or {}

    def splits(self, params: dict | None = None) -> pd.DataFrame:
        return pd.DataFrame(self.paged("/v3/reference/splits", {"limit": 1000, **(params or {})}))

    def dividends(self, params: dict | None = None) -> pd.DataFrame:
        return pd.DataFrame(self.paged("/v3/reference/dividends", {"limit": 1000, **(params or {})}))


def parse_grouped(results: list[dict], day: date) -> pd.DataFrame:
    """Grouped-daily results -> raw bars (ticker,date,open,high,low,close,volume,vwap,n)."""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume", "vwap", "n"]
    if not results:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(results).rename(columns={"T": "ticker", "o": "open", "h": "high",
                                               "l": "low", "c": "close", "v": "volume",
                                               "vw": "vwap"})
    for c in cols:
        if c not in df and c not in ("date",):
            df[c] = pd.NA
    df["date"] = day
    return df[cols]


def save_raw(df: pd.DataFrame, name: str, raw_dir: Path | None = None) -> Path:
    """Write parquet under data/raw/. Refuses to overwrite an existing file."""
    d = Path(raw_dir) if raw_dir else RAW_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.parquet"
    if path.exists():
        raise FileExistsError(f"{path} exists; raw files are never overwritten")
    df.to_parquet(path, index=False)
    return path


def _clean(params: dict) -> dict:
    return {k: v for k, v in params.items() if k.lower() not in ("apikey", "api_key")}


def _strip(url: str) -> str:
    return url.split("?")[0]
