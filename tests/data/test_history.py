"""Offline tests for survivorship-free history building (synthetic frames)."""
from datetime import date

import pandas as pd

from swing import config
from swing.data import history as h


def bars(rows):
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


D = [date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6), date(2020, 1, 7)]


def snaps(rows):
    return pd.DataFrame(rows, columns=["ticker", "snapshot_date", "name", "cik"])


def test_delisted_names_kept_and_availability():
    b = bars([("AAA", D[0], 10, 11, 9, 10, 100), ("AAA", D[1], 10, 11, 9, 10, 100),
              ("ZZZ", D[0], 5, 6, 4, 5, 50),            # ZZZ delists after D[0]
              ("AAA", D[2], 10, 11, 9, 10, 100)])
    s = snaps([("AAA", D[0], "Aaa Inc", "1"), ("ZZZ", D[0], "Zzz Inc", "2")])
    p = h.build_prices(b, s)
    assert set(p["ticker"]) == {"AAA", "ZZZ"}
    assert (p["available_at"] == p["date"].map(config.bar_available_at).pipe(pd.to_datetime, utc=True)).all()
    ref = h.build_reference(p, s)
    r = ref.set_index("ticker")
    assert r.loc["ZZZ", "delist_date"] == D[0] and pd.isna(r.loc["AAA", "delist_date"])
    assert r.loc["AAA", "list_date"] == D[0]


def test_rename_keeps_one_company_and_reuse_gets_two():
    b = bars([("OLD", D[0], 10, 10, 10, 10, 1), ("NEW", D[2], 10, 10, 10, 10, 1),
              ("REU", D[0], 20, 20, 20, 20, 1), ("REU", D[3], 30, 30, 30, 30, 1)])
    s = snaps([("OLD", D[0], "Old Co", "7"), ("NEW", D[2], "New Co", "7"),
               ("REU", D[0], "First Corp", "8"), ("REU", D[3], "Second Corp", "9")])
    p = h.build_prices(b, s)
    cid = p.set_index(["ticker", "date"])["company_id"]
    assert cid[("OLD", D[0])] == cid[("NEW", D[2])]
    assert cid[("REU", D[0])] != cid[("REU", D[3])]
    ref = h.build_reference(p, s).set_index("ticker")
    assert ref.loc["REU", "n_companies"] == 2 and ref.loc["OLD", "n_companies"] == 1
    assert set(ref.loc["REU", "company_names"]) == {"First Corp", "Second Corp"}


def test_split_adjustment_is_backward_and_company_scoped():
    b = bars([("SPL", D[0], 100, 100, 100, 100, 10), ("SPL", D[1], 100, 100, 100, 100, 10),
              ("SPL", D[2], 50, 50, 50, 50, 20)])         # 2-for-1 executed D[2]
    s = snaps([("SPL", D[0], "Spl", "1")])
    sp = pd.DataFrame([("SPL", D[2], 1, 2)], columns=["ticker", "execution_date", "split_from", "split_to"])
    p = h.build_prices(b, s, splits=sp).set_index("date")
    assert p.loc[D[0], "close"] == 50 and p.loc[D[0], "volume"] == 20
    assert p.loc[D[2], "close"] == 50 and p.loc[D[2], "volume"] == 20
    # a different company on the same symbol before the split is not touched
    b2 = bars([("SPL", D[0], 100, 100, 100, 100, 10), ("SPL", D[2], 50, 50, 50, 50, 20)])
    s2 = snaps([("SPL", D[0], "Other", "5"), ("SPL", D[2], "Spl", "1")])
    p2 = h.build_prices(b2, s2, splits=sp).set_index("date")
    assert p2.loc[D[0], "close"] == 100


def test_dividend_adjustment():
    b = bars([("DIV", D[0], 100, 100, 100, 100, 10), ("DIV", D[2], 99, 99, 99, 99, 10)])
    s = snaps([("DIV", D[0], "Div", "1")])
    dv = pd.DataFrame([("DIV", D[2], 1.0)], columns=["ticker", "ex_dividend_date", "cash_amount"])
    p = h.build_prices(b, s, dividends=dv).set_index("date")
    assert abs(p.loc[D[0], "close"] - 99.0) < 1e-9 and p.loc[D[2], "close"] == 99


def test_prices_feed_asof_view():
    from swing.asof import AsOfView, InMemorySource
    b = bars([("AAA", D[0], 10, 11, 9, 10, 100)])
    s = snaps([("AAA", D[0], "Aaa", "1")])
    p = h.build_prices(b, s)
    ref = h.build_reference(p, s)
    v = AsOfView(InMemorySource(p, ref), config.scan_time(D[0]))
    assert len(v.prices()) == 1 and len(v.reference()) == 1


def test_sic_sector_mapping_returns_known_sectors():
    for sic in (3674, 2834, 6022, 1311, 4911, 5411, 7372, 6798, 4813, None, "x"):
        out = h.sic_to_sector(sic)
        assert out is None or out in h.SECTORS
