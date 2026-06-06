from __future__ import annotations

from datetime import datetime
from math import exp

from ..models import Memory, utc_now


class HeatEngine:
    def __init__(self, decay_lambda_per_day: float = 0.03) -> None:
        self.decay_lambda_per_day = decay_lambda_per_day

    def calculate(self, memory: Memory, now: datetime | None = None) -> float:
        return self.explain(memory, now)["heat"]

    def explain(self, memory: Memory, now: datetime | None = None) -> dict[str, float]:
        now = now or utc_now()
        last_touch = memory.accessed_at or memory.updated_at
        age_days = max(0.0, (now - last_touch).total_seconds() / 86_400)
        recency = exp(-self.decay_lambda_per_day * age_days)
        frequency = min(1.0, memory.retrieval_count / 10)
        heat = (
            memory.importance * 0.35
            + frequency * 0.25
            + recency * 0.20
            + memory.relationship_density * 0.10
            + memory.confidence * 0.10
        )
        return {
            "importance": memory.importance,
            "frequency": frequency,
            "recency": recency,
            "relationship_density": memory.relationship_density,
            "confidence": memory.confidence,
            "heat": max(0.0, min(1.0, heat)),
        }
