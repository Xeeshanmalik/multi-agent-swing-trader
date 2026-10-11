"""FROZEN. AsOfView is the only door to the data; it must never show the future."""
from datetime import datetime

import pandas as pd
import pytest

from swing import config
from tests.conftest import build_source, perturb_future, utc


def test_naive_datetime_rejected(source, asof):
    with pytest.raises(ValueError):
        asof.AsOfView(source, datetime(2022, 3, 1, 14, 0))


def test_every_table_filtered(source, asof, sessions):
    as_of = config.scan_time(sessions[300])
    v = asof.AsOfView(source, as_of)
    p, n, lab = v.prices(), v.news(), v.news_labels()
    assert len(p) and len(n) and len(lab)
    assert (pd.to_datetime(p["available_at"], utc=True) <= as_of).all()
    assert (pd.to_datetime(n["first_seen_at"], utc=True) <= as_of).all()
    assert set(lab["item_id"]) <= set(n["item_id"]), "labels must follow their news item's visibility"
    assert len(v.reference()) > 0


def test_label_visibility_follows_news_not_label_rows(asof, frames, sessions):
    as_of = config.scan_time(sessions[300])
    fr = perturb_future(frames, as_of, seed=5)          # adds future items that already have label rows
    v = asof.AsOfView(build_source(fr), as_of)
    future_ids = set(fr["news"].loc[fr["news"]["first_seen_at"] > pd.Timestamp(as_of), "item_id"])
    assert future_ids & set(fr["news_labels"]["item_id"]), "the trap is really there"
    assert not future_ids & set(v.news()["item_id"])
    assert not future_ids & set(v.news_labels()["item_id"])


def test_visibility_uses_first_seen_not_published(asof, frames, sessions):
    as_of = config.scan_time(sessions[300])
    fr = perturb_future(frames, as_of, seed=6)
    late = fr["news"][(fr["news"]["published_at"] <= pd.Timestamp(as_of))
                      & (fr["news"]["first_seen_at"] > pd.Timestamp(as_of))]
    assert len(late) > 0
    v = asof.AsOfView(build_source(fr), as_of)
    assert not set(late["item_id"]) & set(v.news()["item_id"])


def test_bar_timing(source, asof, sessions):
    d, e = sessions[300], sessions[301]
    dates = lambda v: set(pd.to_datetime(v.prices()["date"]).dt.date)
    at_scan = dates(asof.AsOfView(source, config.scan_time(d)))
    assert d in at_scan and e not in at_scan
    at_decision = dates(asof.AsOfView(source, config.decision_time(e)))
    assert d in at_decision and e not in at_decision
    before_close = dates(asof.AsOfView(source, utc(d, 15, 59)))
    assert d not in before_close


def test_lockbox_closed(source, asof):
    assert not config.LOCKBOX_OPEN
    with pytest.raises(config.SealedPeriodError):
        asof.AsOfView(source, config.scan_time(config.LOCKBOX_START))
