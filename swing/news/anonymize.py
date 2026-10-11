"""Strip company identity from news text before any LLM sees it.

Contract: contracts/data.md, "LLM news labels: anti-hindsight rules".
"""
from __future__ import annotations

import re
from typing import Iterable

REPLACEMENT = "the company"
OTHER_REPLACEMENT = "another company"

_MONTHS = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
           r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_DATE_RES = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(rf"\b{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.I),
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\.?,?\s+\d{{4}}\b", re.I),
)


def _alnum_bounded(term: str) -> re.Pattern:
    # Boundaries are "not adjacent to a letter or digit", so ARMQ does not match ARMQX or SWARMQ.
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)


def _replace_terms(text: str, terms: Iterable[str], replacement: str, cashtag: bool = False) -> str:
    terms = sorted({t.strip() for t in terms if t and t.strip()}, key=len, reverse=True)
    for term in terms:
        if cashtag:
            text = re.sub(r"\$" + re.escape(term) + r"(?![A-Za-z0-9])", replacement, text, flags=re.I)
        text = _alnum_bounded(term).sub(replacement, text)
    return text


def anonymize(text: str, ticker: str, company_names: Iterable[str] = (),
              other_names: Iterable[str] = ()) -> str:
    """Replace the ticker, cashtags and every company name with 'the company'.

    `other_names` (tickers/names of other companies in the same article) become
    'another company'. Explicit calendar dates are replaced with 'a date'.
    """
    out = text or ""
    out = _replace_terms(out, other_names, OTHER_REPLACEMENT, cashtag=True)
    # Names first (longest first), then the ticker, then cashtags.
    out = _replace_terms(out, company_names, REPLACEMENT)
    out = _replace_terms(out, [ticker], REPLACEMENT, cashtag=True)
    for rx in _DATE_RES:
        out = rx.sub("a date", out)
    # Tidy repeats such as "the company (the company)" or "the company, the company".
    out = re.sub(r"(the company)\s*\(\s*the company\s*\)", r"\1", out, flags=re.I)
    out = re.sub(r"(the company)(?:\s*[,/]\s*the company)+", r"\1", out, flags=re.I)
    return out
