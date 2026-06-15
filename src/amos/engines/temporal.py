from __future__ import annotations

from datetime import datetime, timezone

from ..models import TemporalFact
from ..ports import TimelineStore


class TemporalTruthEngine:
    def __init__(self, timeline: TimelineStore) -> None:
        self.timeline = timeline

    def update(
        self,
        *,
        tenant_id: str,
        entity: str,
        attribute: str,
        value: str,
        valid_from: datetime,
        source: str,
        memory_id: str | None = None,
        confidence: float = 1.0,
    ) -> tuple[TemporalFact, list[TemporalFact]]:
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=timezone.utc)
        else:
            valid_from = valid_from.astimezone(timezone.utc)
        history = self.timeline.facts(tenant_id, entity, attribute)
        closed: list[TemporalFact] = []

        for fact in history:
            if fact.valid_to is None and fact.value != value:
                if valid_from < fact.valid_from:
                    raise ValueError("valid_from cannot precede the current fact")
                fact.valid_to = valid_from
                self.timeline.put_fact(fact)
                closed.append(fact)
            elif fact.valid_to is None and fact.value == value:
                return fact, closed

        fact = TemporalFact(
            tenant_id=tenant_id,
            entity=entity,
            attribute=attribute,
            value=value,
            valid_from=valid_from,
            source=source,
            memory_id=memory_id,
            confidence=confidence,
        )
        self.timeline.put_fact(fact)
        return fact, closed
