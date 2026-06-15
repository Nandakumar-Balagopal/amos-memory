"""
Adaptive Scheduler with Dynamic Threshold Optimization

This scheduler learns optimal promotion/demotion thresholds from actual usage patterns.
It adjusts thresholds to maintain target tier distributions and memory quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
import statistics

from ..models import LifecycleDecision, Memory, MemoryTier, utc_now
from .heat import HeatEngine


@dataclass
class ThresholdConfig:
    """Dynamic threshold configuration."""
    # Promotion thresholds (heat-based, not survivor count)
    active_to_survivor: float = 0.55  # Lower initial threshold for faster promotion
    survivor_to_durable: float = 0.70  # Lower to allow progression
    
    # Archival thresholds (more aggressive)
    archive_threshold: float = 0.20  # Archive cold memories from any tier
    delete_threshold: float = 0.08   # Delete very cold archived memories
    
    # Learning parameters
    learning_rate: float = 0.08  # Faster learning
    adjustment_interval: int = 100  # Adjust more frequently


@dataclass
class TierStats:
    """Statistics for a memory tier."""
    count: int = 0
    mean_heat: float = 0.0
    median_heat: float = 0.0
    promotion_rate: float = 0.0
    demotion_rate: float = 0.0


@dataclass
class AdaptiveMetrics:
    """Metrics for adaptive learning."""
    evaluations: int = 0
    promotions: int = 0
    demotions: int = 0
    archives: int = 0
    deletions: int = 0
    
    tier_stats: Dict[str, TierStats] | None = None
    
    def __post_init__(self):
        if self.tier_stats is None:
            self.tier_stats = {}


class AdaptiveScheduler:
    """Scheduler that dynamically optimizes thresholds based on usage patterns.
    
    The scheduler learns from:
    1. Tier distribution (target: 60% ACTIVE, 25% SURVIVOR, 10% DURABLE, 5% ARCHIVE)
    2. Heat score distributions per tier
    3. Promotion/demotion success rates
    4. Memory access patterns
    
    It adjusts thresholds to:
    - Maintain healthy tier distribution
    - Promote truly hot memories
    - Archive truly cold memories
    - Minimize thrashing (promote then demote)
    """
    
    def __init__(
        self,
        heat: HeatEngine,
        config: ThresholdConfig | None = None,
        target_distribution: Dict[str, float] | None = None
    ):
        self.heat = heat
        self.config = config or ThresholdConfig()
        self.metrics = AdaptiveMetrics()
        
        # Target tier distribution (percentages)
        self.target_distribution = target_distribution or {
            'ACTIVE': 0.60,      # 60% in active tier
            'SURVIVOR': 0.25,    # 25% in survivor
            'DURABLE': 0.10,     # 10% in durable
            'ARCHIVE': 0.05      # 5% in archive
        }
        
        # Track recent heat scores per tier for analysis
        self.heat_history: Dict[str, List[float]] = {
            'ACTIVE': [],
            'SURVIVOR': [],
            'DURABLE': [],
            'ARCHIVE': []
        }
        self.max_history = 1000  # Keep last 1000 scores per tier
    
    def evaluate(self, memory: Memory, now: datetime | None = None, increment_survivor: bool = True) -> LifecycleDecision:
        """Evaluate memory and make lifecycle decision.
        
        Args:
            memory: Memory to evaluate
            now: Optional simulated time (unused in adaptive scheduler)
            increment_survivor: Whether to increment survivor_count (for compatibility)
        """
        # Calculate current heat
        memory.heat_score = self.heat.calculate(memory, now=now)
        memory.updated_at = now or utc_now()
        
        # Track heat score
        tier_name = memory.tier.value
        if tier_name in self.heat_history:
            self.heat_history[tier_name].append(memory.heat_score)
            if len(self.heat_history[tier_name]) > self.max_history:
                self.heat_history[tier_name].pop(0)
        
        # Make decision using current thresholds
        decision = self._make_decision(memory)
        
        # Track metrics
        self.metrics.evaluations += 1
        if decision == LifecycleDecision.PROMOTE:
            self.metrics.promotions += 1
        elif decision == LifecycleDecision.DEMOTE:
            self.metrics.demotions += 1
        elif decision == LifecycleDecision.ARCHIVE:
            self.metrics.archives += 1
        elif decision == LifecycleDecision.DELETE:
            self.metrics.deletions += 1
        
        # Periodically adjust thresholds
        if self.metrics.evaluations % self.config.adjustment_interval == 0:
            self._adjust_thresholds()
        
        return decision
    
    def _make_decision(self, memory: Memory) -> LifecycleDecision:
        """Make lifecycle decision using current thresholds."""
        heat = memory.heat_score
        
        # ACTIVE → SURVIVOR promotion
        if memory.tier == MemoryTier.ACTIVE and heat >= self.config.active_to_survivor:
            memory.tier = MemoryTier.SURVIVOR
            return LifecycleDecision.PROMOTE
        
        # SURVIVOR → DURABLE promotion
        if memory.tier == MemoryTier.SURVIVOR and heat >= self.config.survivor_to_durable:
            memory.tier = MemoryTier.DURABLE
            return LifecycleDecision.PROMOTE
        
        # Archive cold memories from any tier (except ARCHIVE)
        if memory.tier != MemoryTier.ARCHIVE and heat < self.config.archive_threshold:
            memory.tier = MemoryTier.ARCHIVE
            return LifecycleDecision.ARCHIVE
        
        # ARCHIVE → DELETE
        if memory.tier == MemoryTier.ARCHIVE and heat < self.config.delete_threshold:
            return LifecycleDecision.DELETE
        
        return LifecycleDecision.KEEP
    
    def _adjust_thresholds(self):
        """Adjust thresholds based on observed patterns."""
        # Calculate current tier distribution
        current_dist = self._calculate_tier_distribution()
        
        # Adjust ACTIVE → SURVIVOR threshold
        if current_dist.get('ACTIVE', 0) > self.target_distribution['ACTIVE']:
            # Too many in ACTIVE, lower threshold to promote more
            self.config.active_to_survivor -= self.config.learning_rate
        elif current_dist.get('ACTIVE', 0) < self.target_distribution['ACTIVE']:
            # Too few in ACTIVE, raise threshold to promote less
            self.config.active_to_survivor += self.config.learning_rate
        
        # Adjust SURVIVOR → DURABLE threshold
        if current_dist.get('SURVIVOR', 0) > self.target_distribution['SURVIVOR']:
            # Too many in SURVIVOR, lower threshold to promote more
            self.config.survivor_to_durable -= self.config.learning_rate
        elif current_dist.get('SURVIVOR', 0) < self.target_distribution['SURVIVOR']:
            # Too few in SURVIVOR, raise threshold
            self.config.survivor_to_durable += self.config.learning_rate
        
        # Adjust archiving threshold based on heat distributions
        # Combine all tier heats to find overall cold threshold
        all_heats = []
        for tier_heats in self.heat_history.values():
            all_heats.extend(tier_heats)
        
        if len(all_heats) >= 10:
            sorted_heats = sorted(all_heats)
            # Set archive threshold at 20th percentile
            percentile_20 = sorted_heats[len(sorted_heats) // 5]
            # Gradually move threshold toward target
            target = max(0.15, percentile_20 * 0.95)  # At least 0.15
            self.config.archive_threshold += (target - self.config.archive_threshold) * self.config.learning_rate
        
        # Clamp thresholds to reasonable ranges
        self.config.active_to_survivor = max(0.4, min(0.8, self.config.active_to_survivor))
        self.config.survivor_to_durable = max(0.6, min(0.9, self.config.survivor_to_durable))
        self.config.archive_threshold = max(0.10, min(0.35, self.config.archive_threshold))
        self.config.delete_threshold = max(0.05, min(0.15, self.config.delete_threshold))
    
    def _calculate_tier_distribution(self) -> Dict[str, float]:
        """Calculate current tier distribution from heat history."""
        total = sum(len(scores) for scores in self.heat_history.values())
        if total == 0:
            return {}
        
        return {
            tier: len(scores) / total
            for tier, scores in self.heat_history.items()
            if scores
        }
    
    def get_metrics(self) -> Dict:
        """Get current metrics and threshold values."""
        return {
            'evaluations': self.metrics.evaluations,
            'promotions': self.metrics.promotions,
            'demotions': self.metrics.demotions,
            'archives': self.metrics.archives,
            'deletions': self.metrics.deletions,
            'thresholds': {
                'active_to_survivor': self.config.active_to_survivor,
                'survivor_to_durable': self.config.survivor_to_durable,
                'archive_threshold': self.config.archive_threshold,
                'delete_threshold': self.config.delete_threshold
            },
            'tier_distribution': self._calculate_tier_distribution(),
            'heat_stats': {
                tier: {
                    'count': len(scores),
                    'mean': statistics.mean(scores) if scores else 0,
                    'median': statistics.median(scores) if scores else 0,
                    'min': min(scores) if scores else 0,
                    'max': max(scores) if scores else 0
                }
                for tier, scores in self.heat_history.items()
                if scores
            }
        }
    
    def reset_metrics(self):
        """Reset metrics for new evaluation period."""
        self.metrics = AdaptiveMetrics()
        self.heat_history = {tier: [] for tier in self.heat_history.keys()}
