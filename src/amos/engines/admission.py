from __future__ import annotations

from dataclasses import dataclass

from ..models import MemoryType
from .retrieval import terms


@dataclass
class AdmissionDecision:
    remember: bool
    score: float
    reasons: list[str]


class MemoryAdmissionPolicy:
    """Heuristic gate for deciding whether a turn belongs in long-term memory."""

    TYPE_WEIGHTS: dict[MemoryType, float] = {
        MemoryType.FACT: 0.18,
        MemoryType.SKILL: 0.20,
        MemoryType.PREFERENCE: 0.22,
        MemoryType.BELIEF: 0.14,
        MemoryType.RELATIONSHIP: 0.16,
        MemoryType.SUMMARY: 0.18,
        MemoryType.GOAL: 0.22,
        MemoryType.TASK: 0.18,
        MemoryType.EPISODE: 0.12,
        MemoryType.OBSERVATION: 0.04,
    }
    SIGNAL_TERMS = {
        "always",
        "block",
        "build",
        "building",
        "current",
        "durable",
        "goal",
        "important",
        "memory",
        "prefer",
        "preference",
        "project",
        "reduce",
        "remember",
        "should",
        "store",
        "use",
        "work",
    }
    LOW_VALUE_TERMS = {
        "debug",
        "format",
        "minor",
        "noise",
        "one",
        "output",
        "progress",
        "scratch",
        "temporary",
        "transient",
    }

    def __init__(self, threshold: float = 0.55) -> None:
        self.threshold = threshold

    def evaluate(
        self,
        *,
        content: str,
        type: MemoryType = MemoryType.OBSERVATION,
        importance: float = 0.5,
        confidence: float = 1.0,
    ) -> AdmissionDecision:
        content_terms = terms(content)
        signal_hits = content_terms & self.SIGNAL_TERMS
        low_value_hits = content_terms & self.LOW_VALUE_TERMS
        score = importance * 0.45 + confidence * 0.15 + self.TYPE_WEIGHTS[type]
        score += min(0.15, len(signal_hits) * 0.03)
        score -= min(0.25, len(low_value_hits) * 0.05)
        score = max(0.0, min(1.0, score))

        reasons = [
            f"importance={importance:.2f}",
            f"confidence={confidence:.2f}",
            f"type={type.value}",
            f"type_weight={self.TYPE_WEIGHTS[type]:.2f}",
        ]
        if signal_hits:
            reasons.append("signal_terms=" + ",".join(sorted(signal_hits)))
        if low_value_hits:
            reasons.append("low_value_terms=" + ",".join(sorted(low_value_hits)))
        reasons.append(f"threshold={self.threshold:.2f}")
        return AdmissionDecision(remember=score >= self.threshold, score=round(score, 3), reasons=reasons)
