from __future__ import annotations

from ..models import LifecycleDecision, Memory, MemoryTier, utc_now
from .heat import HeatEngine


class GenerationalScheduler:
    def __init__(self, heat: HeatEngine) -> None:
        self.heat = heat

    def evaluate(self, memory: Memory) -> LifecycleDecision:
        memory.heat_score = self.heat.calculate(memory)
        memory.updated_at = utc_now()

        if memory.tier == MemoryTier.ACTIVE and memory.heat_score >= 0.65:
            memory.tier = MemoryTier.SURVIVOR
            return LifecycleDecision.PROMOTE
        if memory.tier == MemoryTier.SURVIVOR and memory.heat_score >= 0.78:
            memory.tier = MemoryTier.DURABLE
            return LifecycleDecision.PROMOTE
        if memory.tier == MemoryTier.SURVIVOR and memory.heat_score < 0.18:
            memory.tier = MemoryTier.ARCHIVE
            return LifecycleDecision.ARCHIVE
        if memory.tier == MemoryTier.DURABLE and memory.heat_score < 0.20:
            memory.tier = MemoryTier.ARCHIVE
            return LifecycleDecision.DEMOTE
        if memory.tier == MemoryTier.ARCHIVE and memory.heat_score < 0.05:
            return LifecycleDecision.DELETE
        return LifecycleDecision.KEEP

