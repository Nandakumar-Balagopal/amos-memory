from __future__ import annotations

from datetime import datetime
from math import exp

from ..models import Memory, utc_now


class HeatEngine:
    def __init__(
        self,
        decay_lambda_per_day: float = 0.1,
        *,
        recency_weight: float = 0.40,
        frequency_weight: float = 0.25,
        importance_weight: float = 0.20,
        relationship_weight: float = 0.10,
        confidence_weight: float = 0.05,
    ) -> None:
        """Initialize heat engine with exponential decay.
        
        Args:
            decay_lambda_per_day: Decay rate per day (default 0.1 = ~10% daily decay)
                                  Higher values = faster cooling
        """
        self.decay_lambda_per_day = decay_lambda_per_day
        self.recency_weight = recency_weight
        self.frequency_weight = frequency_weight
        self.importance_weight = importance_weight
        self.relationship_weight = relationship_weight
        self.confidence_weight = confidence_weight

    def calculate(self, memory: Memory, now: datetime | None = None) -> float:
        return self.explain(memory, now)["heat"]

    def explain(self, memory: Memory, now: datetime | None = None) -> dict[str, float]:
        """Calculate heat with proper time-based exponential decay.
        
        Heat formula:
        - Base heat from importance (static component)
        - Frequency score from access count (dynamic component)
        - Recency with exponential decay (time-based cooling)
        - Relationship density (graph connectivity)
        - Confidence (data quality)
        
        The key fix: recency now has higher weight and proper exponential decay
        so memories naturally cool down over time without access.
        """
        now = now or utc_now()
        
        # Calculate time since last access. For memories that have never been
        # retrieved, updated_at is the best available last-touch signal.
        last_touch = memory.accessed_at or memory.updated_at or memory.created_at
        age_days = max(0.0, (now - last_touch).total_seconds() / 86_400)
        
        # Exponential decay: e^(-λt)
        # After 7 days with λ=0.1: e^(-0.7) ≈ 0.50 (50% of original)
        # After 14 days: e^(-1.4) ≈ 0.25 (25% of original)
        # After 30 days: e^(-3.0) ≈ 0.05 (5% of original)
        recency = exp(-self.decay_lambda_per_day * age_days)
        
        # Frequency: normalize by expected access count
        # Cap at 1.0 for frequently accessed memories
        frequency = min(1.0, memory.retrieval_count / 10)
        
        # Weighted heat calculation
        # Recency gets highest weight (40%) so time decay dominates
        # Frequency (25%) rewards repeated access
        # Importance (20%) provides base value
        # Graph connectivity (10%) and confidence (5%) are secondary
        heat = (
            recency * self.recency_weight
            + frequency * self.frequency_weight
            + memory.importance * self.importance_weight
            + memory.relationship_density * self.relationship_weight
            + memory.confidence * self.confidence_weight
        )
        
        return {
            "importance": memory.importance,
            "frequency": frequency,
            "recency": recency,
            "age_days": age_days,
            "relationship_density": memory.relationship_density,
            "confidence": memory.confidence,
            "heat": max(0.0, min(1.0, heat)),
        }
