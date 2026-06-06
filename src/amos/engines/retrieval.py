from __future__ import annotations

from collections import Counter
import re
from math import log1p, sqrt

from ..models import Memory, MemoryType, RecallResult, RetrievalRoute


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "does",
    "for",
    "how",
    "is",
    "it",
    "kind",
    "of",
    "the",
    "to",
    "what",
    "which",
}
SYNONYMS = {
    "currently": "current",
    "metrics": "measure",
    "metric": "measure",
    "questions": "query",
    "question": "query",
    "rewritten": "paraphrase",
    "rewrite": "paraphrase",
    "search": "recall",
    "signals": "signal",
    "uses": "use",
    "using": "use",
    "used": "use",
    "retrieval": "recall",
    "retriever": "recall",
    "remembered": "memory",
    "memories": "memory",
    "summaries": "summary",
    "benchmarks": "benchmark",
}
EXPANSIONS = {
    "hot": ("heat",),
    "measure": ("hit", "rate", "token", "compression", "drift"),
    "quality": ("hit", "rate", "drift"),
    "recall": ("retrieval", "search"),
    "semantic": ("meaning",),
    "signal": ("importance", "frequency", "recency", "confidence"),
    "upgrade": ("add", "improve"),
}


def normalize_token(token: str) -> str:
    token = SYNONYMS.get(token.lower(), token.lower())
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 3 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def tokens(text: str, *, include_stopwords: bool = False) -> list[str]:
    result = []
    for match in TOKEN_PATTERN.findall(text.lower()):
        token = normalize_token(match)
        result.append(token)
        result.extend(EXPANSIONS.get(token, ()))
    if include_stopwords:
        return result
    return [token for token in result if token not in STOPWORDS]


def terms(text: str) -> set[str]:
    return set(tokens(text))


def ngrams(text: str) -> Counter[str]:
    normalized = " ".join(tokens(text, include_stopwords=True))
    padded = f" {normalized} "
    return Counter(padded[index:index + 3] for index in range(max(0, len(padded) - 2)))


def cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    dot = sum(left[item] * right[item] for item in common)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class RetrievalRouter:
    ROUTE_HINTS: tuple[tuple[RetrievalRoute, tuple[str, ...]], ...] = (
        (RetrievalRoute.TEMPORAL, ("when", "timeline", "history", "before", "after", "used to")),
        (RetrievalRoute.SKILL, ("skill", "know how", "capable", "expert", "ability")),
        (RetrievalRoute.RELATIONSHIP, ("relationship", "connected", "related", "works with", "depends on")),
        (RetrievalRoute.PREFERENCE, ("prefer", "preference", "favorite", "likes")),
        (RetrievalRoute.TASK, ("task", "todo", "goal", "working on", "next")),
        (RetrievalRoute.CURRENT_STATE, ("current state", "right now", "today", "latest")),
    )

    TYPE_BOOSTS: dict[RetrievalRoute, set[MemoryType]] = {
        RetrievalRoute.SKILL: {MemoryType.SKILL},
        RetrievalRoute.PREFERENCE: {MemoryType.PREFERENCE},
        RetrievalRoute.TASK: {MemoryType.TASK, MemoryType.GOAL},
        RetrievalRoute.RELATIONSHIP: {MemoryType.RELATIONSHIP},
        RetrievalRoute.TEMPORAL: {MemoryType.FACT, MemoryType.EPISODE},
        RetrievalRoute.CURRENT_STATE: {MemoryType.FACT, MemoryType.TASK, MemoryType.GOAL, MemoryType.OBSERVATION},
    }

    def classify(self, query: str) -> RetrievalRoute:
        lowered = query.lower()
        for route, hints in self.ROUTE_HINTS:
            if any(hint in lowered for hint in hints):
                return route
        return RetrievalRoute.GENERAL

    def retrieve(self, query: str, memories: list[Memory], limit: int = 10) -> list[RecallResult]:
        route = self.classify(query)
        query_terms = terms(query)
        query_ngrams = ngrams(query)
        results: list[RecallResult] = []

        for memory in memories:
            content_terms = terms(memory.content)
            overlap = len(query_terms & content_terms) / max(1, len(query_terms))
            semantic = cosine(query_ngrams, ngrams(memory.content))
            type_boost = 0.08 if memory.type in self.TYPE_BOOSTS.get(route, set()) else 0.0
            if overlap == 0 and semantic < 0.12 and type_boost == 0:
                continue
            durable_boost = 0.05 if memory.tier.value == "DURABLE" else 0.0
            frequency_boost = min(0.05, log1p(memory.retrieval_count) / 100)
            score = overlap * 0.50 + semantic * 0.20 + memory.heat_score * 0.12 + memory.confidence * 0.08
            score += type_boost + durable_boost + frequency_boost
            reasons = [
                f"lexical_overlap={overlap:.3f}",
                f"semantic_similarity={semantic:.3f}",
                f"heat={memory.heat_score:.3f}",
            ]
            if type_boost:
                reasons.append(f"route_type_boost={memory.type.value}")
            results.append(RecallResult(memory=memory, score=min(1.0, score), route=route, reasons=reasons))

        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]
