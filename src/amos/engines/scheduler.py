from __future__ import annotations

from datetime import datetime

from ..models import LifecycleDecision, Memory, MemoryTier, utc_now
from .heat import HeatEngine


class GenerationalScheduler:
    """JVM GC-inspired scheduler using survivor count for promotion decisions.
    
    Key principle: Promotion based on survival, not age or heat thresholds.
    Memories must survive multiple GC cycles to prove their value.
    """
    
    def __init__(
        self,
        heat: HeatEngine,
        survivor_threshold_active: int = 3,    # Survive 3 GC cycles to reach SURVIVOR
        survivor_threshold_durable: int = 10,  # Survive 10 GC cycles to reach DURABLE
        heat_threshold_archive: float = 0.1,   # Archive if heat < 0.1
        heat_threshold_delete: float = 0.05,   # Delete if heat < 0.05
    ) -> None:
        self.heat = heat
        self.survivor_threshold_active = survivor_threshold_active
        self.survivor_threshold_durable = survivor_threshold_durable
        self.heat_threshold_archive = heat_threshold_archive
        self.heat_threshold_delete = heat_threshold_delete

    def evaluate(self, memory: Memory, now: datetime | None = None, increment_survivor: bool = True) -> LifecycleDecision:
        """Evaluate memory for lifecycle transition.
        
        Two-phase lifecycle:
        1. GC Phase (increment_survivor=True): Increment survivor count, archive/delete cold memories
        2. Promotion Phase (increment_survivor=False): Check if ready for tier promotion
        
        This separation ensures:
        - GC focuses on cleaning up cold memories
        - Promotion happens independently based on survival count
        - No mass promotions (memories promote individually when ready)
        
        Args:
            memory: Memory to evaluate
            now: Optional simulated time for testing (defaults to utc_now())
            increment_survivor: Whether to increment survivor_count (True for GC, False for promotion checks)
        """
        # Update heat score (includes time-based decay)
        now = now or utc_now()
        memory.heat_score = self.heat.calculate(memory, now=now)
        memory.updated_at = now
        
        # GC PHASE: Archive/delete cold memories from ANY tier
        if increment_survivor:
            memory.survivor_count += 1
            
            # Archive very cold memories (regardless of tier)
            if memory.heat_score < self.heat_threshold_archive and memory.tier != MemoryTier.ARCHIVE:
                memory.tier = MemoryTier.ARCHIVE
                return LifecycleDecision.ARCHIVE
            
            # Delete extremely cold archived memories
            if memory.heat_score < self.heat_threshold_delete and memory.tier == MemoryTier.ARCHIVE:
                return LifecycleDecision.DELETE
            
            # Memory survived this GC cycle
            return LifecycleDecision.KEEP
        
        # PROMOTION PHASE: Check if ready for tier upgrade
        if memory.tier == MemoryTier.ACTIVE:
            if memory.survivor_count >= self.survivor_threshold_active:
                memory.tier = MemoryTier.SURVIVOR
                return LifecycleDecision.PROMOTE
        
        elif memory.tier == MemoryTier.SURVIVOR:
            if memory.survivor_count >= self.survivor_threshold_durable:
                memory.tier = MemoryTier.DURABLE
                return LifecycleDecision.PROMOTE
        
        return LifecycleDecision.KEEP

