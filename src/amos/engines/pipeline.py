from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from ..models import Relationship, TemporalFact


@dataclass(slots=True)
class FactCandidate:
    entity: str
    attribute: str
    value: str
    confidence: float


@dataclass(slots=True)
class RelationshipCandidate:
    source: str
    relation: str
    target: str
    confidence: float


@dataclass(slots=True)
class ProcessingReport:
    memory_id: str
    extracted_facts: list[TemporalFact] = field(default_factory=list)
    extracted_relationships: list[Relationship] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class DeterministicMemoryPipeline:
    """A conservative local pipeline for first-pass extraction.

    This is intentionally deterministic. LLM extractors can be added behind the
    same contract later, but AMOS should already have explainable behavior when
    no model is available.
    """

    FACT_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
        (re.compile(r"\b(?P<entity>[A-Z][\w-]*)\s+(?:is\s+)?building\s+(?P<value>[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)", re.I), "works_on", "WORKS_ON"),
        (re.compile(r"\b(?P<entity>[A-Z][\w-]*)\s+(?:works|worked|started working)\s+on\s+(?P<value>[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)", re.I), "works_on", "WORKS_ON"),
        (re.compile(r"\b(?P<entity>[A-Z][\w-]*)\s+uses\s+(?P<value>[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)", re.I), "uses", "USES"),
        (re.compile(r"\b(?P<entity>[A-Z][\w-]*)\s+prefers\s+(?P<value>[^.]+)", re.I), "prefers", "PREFERS"),
    )

    RELATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\b(?P<source>[A-Z][\w-]*)\s+depends\s+on\s+(?P<target>[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)", re.I), "DEPENDS_ON"),
        (re.compile(r"\b(?P<source>[A-Z][\w-]*)\s+is\s+related\s+to\s+(?P<target>[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)", re.I), "RELATED_TO"),
    )

    def extract_facts(self, content: str) -> list[FactCandidate]:
        candidates: list[FactCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for pattern, attribute, _relation in self.FACT_PATTERNS:
            for match in pattern.finditer(content):
                entity = self._clean(match.group("entity"))
                value = self._clean(match.group("value"))
                key = (entity.lower(), attribute, value.lower())
                if entity and value and key not in seen:
                    seen.add(key)
                    candidates.append(FactCandidate(entity, attribute, value, 0.72))
        return candidates

    def extract_relationships(self, content: str) -> list[RelationshipCandidate]:
        candidates: list[RelationshipCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for pattern, attribute, relation in self.FACT_PATTERNS:
            for match in pattern.finditer(content):
                source = self._clean(match.group("entity"))
                target = self._clean(match.group("value"))
                key = (source.lower(), relation, target.lower())
                if source and target and key not in seen:
                    seen.add(key)
                    candidates.append(RelationshipCandidate(source, relation, target, 0.72))
        for pattern, relation in self.RELATION_PATTERNS:
            for match in pattern.finditer(content):
                source = self._clean(match.group("source"))
                target = self._clean(match.group("target"))
                key = (source.lower(), relation, target.lower())
                if source and target and key not in seen:
                    seen.add(key)
                    candidates.append(RelationshipCandidate(source, relation, target, 0.78))
        return candidates

    def valid_from(self, _content: str) -> datetime | None:
        return None

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip(" .,:;!?\"'")).strip()

