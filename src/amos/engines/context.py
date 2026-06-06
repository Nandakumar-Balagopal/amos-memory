from __future__ import annotations

from ..models import CompiledContext, RecallResult


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


class ContextCompiler:
    def compile(self, candidates: list[RecallResult], token_budget: int) -> CompiledContext:
        if token_budget < 1:
            raise ValueError("token_budget must be positive")

        selected: list[RecallResult] = []
        rejected: list[RecallResult] = []
        seen: set[str] = set()
        lines: list[str] = []
        used = 0

        for candidate in candidates:
            normalized = " ".join(candidate.memory.content.lower().split())
            line = f"[{candidate.memory.type.value}] {candidate.memory.content}"
            cost = estimate_tokens(line)
            if normalized in seen or used + cost > token_budget:
                rejected.append(candidate)
                continue
            seen.add(normalized)
            selected.append(candidate)
            lines.append(line)
            used += cost

        route = candidates[0].route if candidates else self._general_route()
        return CompiledContext(
            text="\n".join(lines),
            token_count=used,
            selected=selected,
            rejected=rejected,
            route=route,
        )

    @staticmethod
    def _general_route():
        from ..models import RetrievalRoute

        return RetrievalRoute.GENERAL

