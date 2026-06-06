from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Signal:
    turn: int
    content: str
    type: str
    importance: float
    probe: str
    expected: str
    paraphrase: str


SIGNALS: list[Signal] = [
    Signal(1, "Nandu is building AMOS", "EPISODE", 0.95, "What is Nandu building?", "Nandu is building AMOS", "Which project is Nandu creating?"),
    Signal(4, "AMOS should reduce long-term prompt token usage while preserving important context", "GOAL", 0.95, "What should AMOS reduce over the long term?", "reduce long-term prompt token usage", "What cost should the memory system lower over time?"),
    Signal(8, "Nandu prefers concise benchmark summaries with exact latency numbers", "PREFERENCE", 0.82, "What kind of benchmark summaries does Nandu prefer?", "concise benchmark summaries", "How should benchmark results be reported to Nandu?"),
    Signal(12, "AMOS uses Postgres as the durable source of truth for memories and domain events", "FACT", 0.86, "What durable source of truth does AMOS use?", "Postgres", "Where is authoritative durable memory stored?"),
    Signal(16, "AMOS uses Redis as a write-through L1 cache for memory reads", "FACT", 0.82, "What does AMOS use Redis for?", "write-through L1 cache", "Which component is the fast cache layer?"),
    Signal(20, "AMOS uses Neo4j for relationship graph storage", "FACT", 0.82, "What graph storage does AMOS use?", "Neo4j", "Where are relationship edges kept?"),
    Signal(28, "The AMOS MCP benchmark stores memories through JSON-RPC tool calls", "FACT", 0.78, "How does the AMOS MCP benchmark store memories?", "JSON-RPC tool calls", "What protocol path writes benchmark memories?"),
    Signal(36, "AMOS recall is currently lexical rather than semantic", "OBSERVATION", 0.88, "What kind of recall does AMOS currently use?", "lexical", "Is recall based on meaning or word matching today?"),
    Signal(44, "AMOS should add semantic retrieval to improve paraphrase recall", "TASK", 0.9, "What retrieval improvement should AMOS add?", "semantic retrieval", "What search upgrade would help rewritten questions?"),
    Signal(52, "AMOS should add durable local storage such as SQLite for personal Codex memory", "TASK", 0.86, "What local durable storage should AMOS consider?", "SQLite", "Which lightweight database is suitable for personal memory?"),
    Signal(64, "AMOS safe forgetting blocks deletion when consolidated memories depend on a source", "FACT", 0.84, "When should AMOS block deletion?", "consolidated memories depend on a source", "Why might forgetting a source memory be denied?"),
    Signal(76, "AMOS heat scoring combines importance frequency recency relationship density and confidence", "FACT", 0.83, "What does AMOS heat scoring combine?", "importance frequency recency", "Which signals make a memory hot?"),
    Signal(88, "AMOS context compilation deduplicates memories and respects a token budget", "FACT", 0.84, "What does AMOS context compilation respect?", "token budget", "What limit constrains compiled context?"),
    Signal(100, "Long horizon AMOS testing should measure hit rate token compression and context drift", "GOAL", 0.93, "What should long horizon AMOS testing measure?", "hit rate token compression", "Which metrics prove long-running memory quality?"),
    Signal(112, "AMOS hybrid mode persists memories in Postgres caches them in Redis and stores relationships in Neo4j", "SUMMARY", 0.88, "Where does AMOS hybrid mode persist cache and store relationships?", "Postgres caches them in Redis", "How are database cache and graph roles split in hybrid mode?"),
]


NOISE_TOPICS = [
    "temporary terminal output",
    "minor wording changes",
    "one-off PowerShell commands",
    "short-lived Docker pull progress",
    "formatting experiments",
    "local timing variance",
    "scratch notes",
    "transient debug output",
]


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def noise_turn(turn: int) -> str:
    topic = NOISE_TOPICS[turn % len(NOISE_TOPICS)]
    return (
        f"Turn {turn}: discussed {topic}; this note is useful for the moment "
        f"but should not dominate future long-term context."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate AMOS long-horizon context compression and recall.")
    parser.add_argument("--backend", choices=["memory", "sqlite", "hybrid"], default="memory")
    parser.add_argument("--turns", type=int, default=120)
    parser.add_argument("--token-budget", type=int, default=160)
    parser.add_argument("--include-paraphrases", action="store_true")
    parser.add_argument(
        "--policy",
        choices=["selected", "admitted", "store-all"],
        default="selected",
        help="selected stores durable signals; admitted applies AMOS admission policy; store-all stores every turn.",
    )
    parser.add_argument("--tenant-id", default=f"long-horizon-{int(time.time())}")
    parser.add_argument("--output-dir", default=str(ROOT / "benchmark-results"))
    return parser.parse_args()


def build_service(backend: str):
    os.environ["AMOS_STORAGE_BACKEND"] = backend
    if backend == "sqlite":
        os.environ.setdefault("AMOS_SQLITE_PATH", str(ROOT / ".amos-eval.sqlite3"))
    if backend == "hybrid":
        os.environ.setdefault("AMOS_POSTGRES_DSN", "postgresql://amos:amos@127.0.0.1:5432/amos")
        os.environ.setdefault("AMOS_REDIS_URL", "redis://127.0.0.1:6379/0")
        os.environ.setdefault("AMOS_NEO4J_URI", "bolt://127.0.0.1:7687")
        os.environ.setdefault("AMOS_NEO4J_USER", "neo4j")
        os.environ.setdefault("AMOS_NEO4J_PASSWORD", "amos-password")

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from amos.runtime import build_amos

    return build_amos()


def run_eval(args: argparse.Namespace) -> dict[str, Any]:
    amos = build_service(args.backend)
    from amos.models import MemoryType

    signal_by_turn = {signal.turn: signal for signal in SIGNALS if signal.turn <= args.turns}
    transcript: list[str] = []
    probes: list[dict[str, Any]] = []
    write_latencies: list[float] = []
    context_latencies: list[float] = []

    for turn in range(1, args.turns + 1):
        signal = signal_by_turn.get(turn)
        text = signal.content if signal else noise_turn(turn)
        transcript.append(f"user/agent turn {turn}: {text}")

        should_store = bool(signal) or args.policy == "store-all"
        admission = None
        if args.policy == "admitted":
            admission = amos.assess_memory(
                content=text,
                type=MemoryType(signal.type if signal else "OBSERVATION"),
                importance=signal.importance if signal else 0.15,
                confidence=1.0 if signal else 0.55,
            )
            should_store = admission.remember

        if should_store:
            started = time.perf_counter()
            amos.remember(
                tenant_id=args.tenant_id,
                content=text,
                type=MemoryType(signal.type if signal else "OBSERVATION"),
                importance=signal.importance if signal else 0.15,
                confidence=1.0 if signal else 0.55,
                metadata={
                    "long_horizon_turn": turn,
                    "signal": bool(signal),
                    "admission_score": admission.score if admission else None,
                    "admission_reasons": admission.reasons if admission else [],
                },
            )
            write_latencies.append((time.perf_counter() - started) * 1000)

        if turn % 20 == 0 or turn == args.turns:
            baseline_tokens = estimate_tokens("\n".join(transcript))
            eligible = [item for item in SIGNALS if item.turn <= turn]
            queries: list[tuple[Signal, str, str]] = [(item, item.probe, "direct") for item in eligible]
            if args.include_paraphrases:
                queries.extend((item, item.paraphrase, "paraphrase") for item in eligible)
            for item, query, query_kind in queries:
                started = time.perf_counter()
                context = amos.get_context(
                    tenant_id=args.tenant_id,
                    query=query,
                    token_budget=args.token_budget,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                context_latencies.append(elapsed_ms)
                hit = item.expected.lower() in context.text.lower()
                probes.append(
                    {
                        "turn": turn,
                        "signal_turn": item.turn,
                        "query": query,
                        "query_kind": query_kind,
                        "expected": item.expected,
                        "hit": hit,
                        "baseline_tokens": baseline_tokens,
                        "amos_context_tokens": context.token_count,
                        "compression_ratio": round(baseline_tokens / max(1, context.token_count), 2),
                        "latency_ms": round(elapsed_ms, 3),
                        "selected_count": len(context.selected),
                        "rejected_count": len(context.rejected),
                        "context": context.text,
                    }
                )

    hits = [probe["hit"] for probe in probes]
    compression = [probe["compression_ratio"] for probe in probes]
    misses = [probe for probe in probes if not probe["hit"]]
    return {
        "backend": args.backend,
        "policy": args.policy,
        "tenant_id": args.tenant_id,
        "turns": args.turns,
        "token_budget": args.token_budget,
        "ran_at": datetime.now(UTC).isoformat(),
        "summary": {
            "stored_memory_count": len(write_latencies),
            "probe_count": len(probes),
            "hit_count": sum(1 for hit in hits if hit),
            "hit_rate": round(sum(1 for hit in hits if hit) / max(1, len(hits)), 3),
            "avg_compression_ratio": round(statistics.fmean(compression), 2) if compression else 0.0,
            "latest_baseline_tokens": estimate_tokens("\n".join(transcript)),
            "token_budget": args.token_budget,
            "avg_write_latency_ms": round(statistics.fmean(write_latencies), 3) if write_latencies else 0.0,
            "avg_context_latency_ms": round(statistics.fmean(context_latencies), 3) if context_latencies else 0.0,
            "miss_count": len(misses),
        },
        "misses": [
            {
                "turn": miss["turn"],
                "signal_turn": miss["signal_turn"],
                "query": miss["query"],
                "expected": miss["expected"],
                "context": miss["context"],
            }
            for miss in misses[:20]
        ],
        "probes": probes,
    }


def main() -> None:
    args = parse_args()
    report = run_eval(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"amos-long-horizon-{args.backend}-{args.policy}-{args.tenant_id}.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"report_path": str(output_path), **report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
