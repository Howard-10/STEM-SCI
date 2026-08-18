"""Deterministic normalisation shared by graph, sparse and dense retrieval."""

from __future__ import annotations

import re
import unicodedata


_WORD_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+")
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_TRAILING_DOI_PUNCTUATION = re.compile(r"[\s.,;:)}\]]+$")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

# The lexicon is intentionally small, explicit and versionable. It is not an LLM
# query rewrite, and preserves the original query in the retrieval trace.
_QUERY_EXPANSIONS = {
    "生成式ai": "generative ai",
    "生成式人工智能": "generative ai",
    "人工智能": "artificial intelligence ai",
    "支架": "scaffolding instructional scaffolding",
    "物理": "physics physics education",
    "建模": "modelling modeling",
    "项目式学习": "project based learning pbl",
    "探究式学习": "inquiry based learning",
    "师范生": "pre service teachers preservice teachers",
    "学习迁移": "transfer learning transfer",
    "提示依赖": "prompt dependency overreliance",
}

_CHINESE_SEGMENTS = tuple(sorted(_QUERY_EXPANSIONS, key=len, reverse=True))


def normalize_text(value: str) -> str:
    """Produce a stable Unicode/case-folded form without changing meaning."""

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_doi(value: str | None) -> str | None:
    """Normalise a DOI when one is present; otherwise retain its absence."""

    if not value:
        return None
    normalized = normalize_text(value)
    normalized = _DOI_PREFIX.sub("", normalized)
    normalized = _TRAILING_DOI_PUNCTUATION.sub("", normalized)
    return normalized or None


def tokenize(value: str) -> list[str]:
    """Return deterministic bilingual search tokens, excluding English stopwords."""

    return [token for token in _WORD_PATTERN.findall(normalize_text(value)) if token not in _STOPWORDS]


def expanded_query(query: str) -> str:
    """Append transparent bilingual retrieval hints for the bounded Physics-STEM lexicon."""

    normalized = normalize_text(query)
    additions = [english for chinese, english in _QUERY_EXPANSIONS.items() if chinese in normalized]
    # A compact Chinese query has no whitespace. Segment only our transparent,
    # bounded domain lexicon so "生成式AI支架物理建模师范生" preserves the
    # same retrieval concepts as the spaced equivalent without pretending to
    # perform a general-purpose LLM query rewrite.
    segmented = normalized
    for phrase in _CHINESE_SEGMENTS:
        segmented = segmented.replace(phrase, f" {phrase} ")
    return " ".join([normalized, segmented, *additions])
