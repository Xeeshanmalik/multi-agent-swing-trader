import pandas as pd
import pytest

from swing import config
from swing.asof import AsOfView, InMemorySource
from swing.data import store, universe
from tests.conftest import make_frames


@pytest.fixture(scope="module")
def fr():
    return make_frames(n_tickers=30, n_delisted=2)


def test_roundtrip_matches_in_memory(fr, tmp_path):
    store.write_tables(tmp_path, **fr)
    ps, ms = store.ParquetSource(tmp_path), InMemorySource(**fr)
    d = sorted(fr["prices"]["date"].unique())[300]
    a = AsOfView(ps, config.scan_time(d))
    b = AsOfView(ms, config.scan_time(d))
    for name in ("prices", "news", "news_labels", "reference"):
        x = getattr(a, name)().reset_index(drop=True)
        y = getattr(b, name)().reset_index(drop=True)
        pd.testing.assert_frame_equal(x, y, check_dtype=False)
    pd.testing.assert_frame_equal(universe.members(a, d).reset_index(drop=True),
                                  universe.members(b, d).reset_index(drop=True))


def test_never_overwrites(fr, tmp_path):
    store.write_tables(tmp_path, fr["prices"], fr["reference"])
    with pytest.raises(FileExistsError):
        store.write_tables(tmp_path, fr["prices"], fr["reference"])


def test_news_optional_and_missing_root(fr, tmp_path):
    store.write_tables(tmp_path, fr["prices"], fr["reference"])
    v = AsOfView(store.ParquetSource(tmp_path), config.scan_time(fr["prices"]["date"].max()))
    assert len(v.news()) == 0 and len(v.news_labels()) == 0
    with pytest.raises(FileNotFoundError):
        store.ParquetSource(tmp_path / "nope")
