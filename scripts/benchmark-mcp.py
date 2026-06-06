from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


MEMORIES: list[dict[str, Any]] = [
    {
        "content": "Nandu is building AMOS",
        "type": "EPISODE",
        "importance": 0.9,
    },
    {
        "content": "AMOS uses Postgres as the source of truth for memories and domain events",
        "type": "FACT",
        "importance": 0.85,
    },
    {
        "content": "AMOS uses Redis as a write-through L1 cache for memory reads",
        "type": "FACT",
        "importance": 0.8,
    },
    {
        "content": "AMOS uses Neo4j for relationship graph storage",
        "type": "FACT",
        "importance": 0.8,
    },
    {
        "content": "AMOS exposes a dependency-free JSON HTTP API on localhost port 8080",
        "type": "FACT",
        "importance": 0.7,
    },
    {
        "content": "AMOS supports MCP tools for remember recall context timeline relationships and explain memory",
        "type": "SKILL",
        "importance": 0.85,
    },
    {
        "content": "Nandu prefers concise benchmark summaries with exact latency numbers",
        "type": "PREFERENCE",
        "importance": 0.75,
    },
    {
        "content": "Current prototype testing focuses on real-world Codex memory workflows",
        "type": "TASK",
        "importance": 0.8,
    },
    {
        "content": "AMOS lifecycle promotes hot active memories into survivor and durable tiers",
        "type": "FACT",
        "importance": 0.7,
    },
    {
        "content": "AMOS archives cold survivor memories and blocks unsafe deletion when dependents exist",
        "type": "FACT",
        "importance": 0.75,
    },
    {
        "content": "The deterministic pipeline extracts facts and relationships after memory writes",
        "type": "SUMMARY",
        "importance": 0.7,
    },
    {
        "content": "Temporal facts in AMOS are stored as non-overlapping intervals",
        "type": "FACT",
        "importance": 0.8,
    },
]


QUERIES: list[dict[str, Any]] = [
    {"query": "What is Nandu building?", "limit": 5},
    {"query": "What storage does AMOS use?", "limit": 5},
    {"query": "What does AMOS use Redis for?", "limit": 5},
    {"query": "What MCP tools does AMOS support?", "limit": 5},
    {"query": "What is the current prototype testing focus?", "limit": 5},
    {"query": "What does Nandu prefer for benchmark summaries?", "limit": 5},
    {"query": "How does AMOS lifecycle handle hot and cold memories?", "limit": 5},
]


class McpClient:
    def __init__(self, backend: str) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["AMOS_STORAGE_BACKEND"] = backend
        if backend == "sqlite":
            env.setdefault("AMOS_SQLITE_PATH", str(ROOT / ".amos-benchmark.sqlite3"))
        self.process = subprocess.Popen(
            [sys.executable, "-m", "amos.mcp"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._next_id = 1

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def call(self, method: str, params: dict[str, Any] | None = None) -> tuple[dict[str, Any], float]:
        request = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        self._next_id += 1
        if params is not None:
            request["params"] = params

        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("MCP process pipes are unavailable")

        started = time.perf_counter()
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        elapsed_ms = (time.perf_counter() - started) * 1000

        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"MCP server exited without a response. stderr={stderr}")
        response = json.loads(line)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response, elapsed_ms


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * pct))
    return ordered[index]


def stats(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "min_ms": round(min(values), 3) if values else 0.0,
        "avg_ms": round(statistics.fmean(values), 3) if values else 0.0,
        "p50_ms": round(statistics.median(values), 3) if values else 0.0,
        "p95_ms": round(percentile(values, 0.95), 3),
        "max_ms": round(max(values), 3) if values else 0.0,
    }


def tool_call(client: McpClient, name: str, arguments: dict[str, Any]) -> tuple[Any, float]:
    response, elapsed_ms = client.call(
        "tools/call",
        {"name": name, "arguments": arguments},
    )
    return response["result"]["structuredContent"], elapsed_ms


def run(backend: str, tenant_id: str) -> dict[str, Any]:
    client = McpClient(backend)
    try:
        initialize, initialize_ms = client.call(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "amos-mcp-benchmark", "version": "0.1.0"},
            },
        )
        tools, tools_ms = client.call("tools/list")

        writes = []
        for index, memory in enumerate(MEMORIES, start=1):
            payload = {
                "tenant_id": tenant_id,
                "content": memory["content"],
                "type": memory["type"],
                "importance": memory["importance"],
                "confidence": memory.get("confidence", 1.0),
                "metadata": {"benchmark_index": index},
            }
            structured, elapsed_ms = tool_call(client, "remember", payload)
            writes.append(
                {
                    "index": index,
                    "id": structured["id"],
                    "type": structured["type"],
                    "content": structured["content"],
                    "elapsed_ms": round(elapsed_ms, 3),
                    "heat_score": structured["heat_score"],
                    "extracted": {
                        "processed": bool(structured["metadata"].get("pipeline_processed_at")),
                        "pipeline_version": structured["metadata"].get("pipeline_version"),
                    },
                }
            )

        recalls = []
        for query in QUERIES:
            structured, elapsed_ms = tool_call(
                client,
                "recall",
                {"tenant_id": tenant_id, "query": query["query"], "limit": query["limit"]},
            )
            items = structured["items"]
            recalls.append(
                {
                    "query": query["query"],
                    "elapsed_ms": round(elapsed_ms, 3),
                    "result_count": len(items),
                    "route": items[0]["route"] if items else "NONE",
                    "top_results": [
                        {
                            "score": item["score"],
                            "type": item["memory"]["type"],
                            "content": item["memory"]["content"],
                            "reasons": item["reasons"],
                        }
                        for item in items[:3]
                    ],
                }
            )

        context, context_ms = tool_call(
            client,
            "get_context",
            {
                "tenant_id": tenant_id,
                "query": "Summarize AMOS storage, MCP, and benchmark preferences",
                "token_budget": 120,
            },
        )

        write_latencies = [item["elapsed_ms"] for item in writes]
        recall_latencies = [item["elapsed_ms"] for item in recalls]
        return {
            "backend": backend,
            "tenant_id": tenant_id,
            "ran_at": datetime.now(UTC).isoformat(),
            "mcp": {
                "initialize_ms": round(initialize_ms, 3),
                "tools_list_ms": round(tools_ms, 3),
                "server": initialize["result"]["serverInfo"],
                "tool_names": [tool["name"] for tool in tools["result"]["tools"]],
            },
            "summary": {
                "memory_count": len(writes),
                "query_count": len(recalls),
                "write_latency": stats(write_latencies),
                "recall_latency": stats(recall_latencies),
                "context_latency_ms": round(context_ms, 3),
                "context_token_count": context["token_count"],
            },
            "writes": writes,
            "recalls": recalls,
            "context": {
                "elapsed_ms": round(context_ms, 3),
                "token_count": context["token_count"],
                "route": context["route"],
                "text": context["text"],
            },
        }
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark AMOS through its MCP stdio server.")
    parser.add_argument("--backend", choices=["memory", "sqlite", "hybrid"], default="memory")
    parser.add_argument("--tenant-id", default=f"mcp-benchmark-{int(time.time())}")
    parser.add_argument("--output-dir", default=str(ROOT / "benchmark-results"))
    args = parser.parse_args()

    report = run(args.backend, args.tenant_id)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"amos-mcp-{args.backend}-{args.tenant_id}.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"report_path": str(output_path), **report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
