"""FROZEN. The LLM labeler must never see who the company is, and must be reproducible."""
import re

import pandas as pd

from tests.conftest import CATEGORIES, require


class RecordingClient:
    """Stands in for the LLM. Records every text it is asked to classify."""

    def __init__(self):
        self.texts = []

    def classify(self, text: str) -> dict:
        self.texts.append(text)
        neg = any(w in text.lower() for w in ("slide", "drop", "probe", "cut", "falls"))
        return {"sentiment": "negative" if neg else "neutral",
                "category": "analyst_rating" if "downgrade" in text else "other",
                "persistence": "non_fundamental" if "downgrade" in text else "unclear"}


def test_anonymize_removes_identity():
    anon = require("swing.news.anonymize")
    names = ("Acme Widgets Corp", "Acme Holdings")
    text = ("Acme Widgets Corp (ACMQ) shares slide after downgrade; $ACMQ down. "
            "ACME HOLDINGS said acme widgets corp's outlook is fine. ACMQ's CEO left.")
    out = anon.anonymize(text, "ACMQ", names)
    low = out.lower()
    assert "acmq" not in low
    assert "acme widgets corp" not in low and "acme holdings" not in low
    assert "downgrade" in low and "slide" in low, "event words must survive"
    assert "the company" in low


def test_anonymize_respects_word_boundaries():
    anon = require("swing.news.anonymize")
    out = anon.anonymize("ARMQ rallies while ARMQX and SWARMQ do not.", "ARMQ", ("Arm Q Inc",))
    assert "ARMQX" in out and "SWARMQ" in out
    assert not re.search(r"\bARMQ\b", out)


def test_classifier_only_sees_anonymized_text(frames):
    classify = require("swing.news.classify")
    assert tuple(classify.CATEGORIES) == CATEGORIES
    assert isinstance(classify.PROMPT_HASH, str) and len(classify.PROMPT_HASH) >= 8
    news = frames["news"].head(60).copy()
    ref = frames["reference"]
    client = RecordingClient()
    labels = classify.classify_items(news, ref, client, model_id="stub-model")
    assert len(client.texts) >= len(news)
    forbidden = set()
    for tks in news["tickers"]:
        for t in tks:
            forbidden.add(t.lower())
            for nm in ref.loc[ref["ticker"] == t, "company_names"].iloc[0]:
                forbidden.add(nm.lower())
    for txt in client.texts:
        low = txt.lower()
        for word in forbidden:
            assert not re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", low), \
                f"classifier saw {word!r}"
    # Output contract
    assert {"item_id", "ticker", "sentiment", "category", "persistence",
            "prompt_hash", "model_id"} <= set(labels.columns)
    expected = {(i, t) for i, tks in zip(news["item_id"], news["tickers"]) for t in tks}
    assert set(zip(labels["item_id"], labels["ticker"])) == expected
    assert labels["sentiment"].isin(["negative", "neutral", "positive"]).all()
    assert labels["persistence"].isin(["fundamental", "non_fundamental", "unclear"]).all()
    assert labels["category"].isin(CATEGORIES).all()
    assert (labels["prompt_hash"] == classify.PROMPT_HASH).all()
    assert (labels["model_id"] == "stub-model").all()


def test_classifier_rejects_invalid_model_output(frames):
    classify = require("swing.news.classify")

    class BadClient:
        def classify(self, text):
            return {"sentiment": "very bad", "category": "gossip", "persistence": "forever"}

    labels = classify.classify_items(frames["news"].head(5), frames["reference"], BadClient(),
                                     model_id="stub-model")
    # Invalid outputs must be coerced to safe values, never passed through.
    assert labels["sentiment"].isin(["negative", "neutral", "positive"]).all()
    assert labels["category"].isin(CATEGORIES).all()
    assert (labels["persistence"] == "unclear").all()
