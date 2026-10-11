"""Offline tests for the Massive client: a fake session, no network, no key."""
import json
from datetime import date

import pytest

from swing.data import massive


class Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._p, self.headers = status, payload or {}, headers or {}

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        return self.responses.pop(0)


def client(tmp_path, responses, **kw):
    sleeps = []
    c = massive.MassiveClient(FakeSession(responses), key_getter=lambda: "SECRET",
                              manifest_path=tmp_path / "manifest.jsonl",
                              sleep=sleeps.append, min_interval=0.0, **kw)
    return c, sleeps


def test_grouped_daily_parses_and_logs(tmp_path):
    res = [{"T": "AAA", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100, "vw": 1.2, "n": 7}]
    c, _ = client(tmp_path, [Resp(200, {"results": res})])
    df = c.grouped_daily(date(2020, 1, 2))
    assert list(df["ticker"]) == ["AAA"] and df["date"].iloc[0] == date(2020, 1, 2)
    line = json.loads((tmp_path / "manifest.jsonl").read_text())
    assert line["rows"] == 1 and "grouped" in line["endpoint"] and line["retrieved_at"]
    assert "SECRET" not in json.dumps(line)


def test_key_in_header_not_url(tmp_path):
    c, _ = client(tmp_path, [Resp(200, {"results": []})])
    c.grouped_daily(date(2020, 1, 2))
    url, params, headers = c._session.calls[0]
    assert "SECRET" not in url and "SECRET" not in str(params)
    assert headers["Authorization"] == "Bearer SECRET"


def test_retries_then_succeeds(tmp_path):
    c, sleeps = client(tmp_path, [Resp(429, headers={"Retry-After": "2"}), Resp(503),
                                  Resp(200, {"results": []})])
    c.get("/x")
    assert sleeps[0] == 2.0 and len(sleeps) == 2


def test_gives_up_and_fails_hard_on_4xx(tmp_path):
    c, _ = client(tmp_path, [Resp(500)] * 3, max_retries=2)
    with pytest.raises(massive.MassiveError):
        c.get("/x")
    c, _ = client(tmp_path, [Resp(403)])
    with pytest.raises(massive.MassiveError):
        c.get("/x")


def test_pagination_follows_next_url(tmp_path):
    c, _ = client(tmp_path, [Resp(200, {"results": [{"a": 1}], "next_url": "https://h/next?cursor=z"}),
                             Resp(200, {"results": [{"a": 2}]})])
    assert len(c.paged("/v3/reference/tickers", {"limit": 1})) == 2
    assert c._session.calls[1][0] == "https://h/next?cursor=z"
    assert json.loads((tmp_path / "manifest.jsonl").read_text())["pages"] == 2


def test_throttle_spaces_requests(tmp_path):
    sleeps, t = [], [0.0]
    c = massive.MassiveClient(FakeSession([Resp(200), Resp(200)]), key_getter=lambda: "k",
                              manifest_path=tmp_path / "m.jsonl", min_interval=0.5,
                              sleep=sleeps.append, clock=lambda: t[0])
    c.get("/a"); c.get("/b")
    assert sleeps == [0.5]


def test_save_raw_never_overwrites(tmp_path):
    import pandas as pd
    df = pd.DataFrame({"a": [1]})
    massive.save_raw(df, "x", tmp_path)
    with pytest.raises(FileExistsError):
        massive.save_raw(df, "x", tmp_path)


def test_no_key_read_at_construction(tmp_path):
    massive.MassiveClient(manifest_path=tmp_path / "m.jsonl")   # must not touch env
