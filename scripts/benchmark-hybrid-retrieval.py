#!/usr/bin/env python3
"""Benchmark V2 hybrid retrieval vs V1 lexical retrieval.

This script compares:
1. Retrieval quality (semantic relevance)
2. Query latency
3. Embedding generation overhead
4. Memory usage

Usage:
    python scripts/benchmark-hybrid-retrieval.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Tuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from amos import Amos
from amos.models import Memory, MemoryType, MemoryScope
from amos.stores import InMemoryStorage, PostgresStorage


# Test dataset: queries with expected relevant memories
TEST_QUERIES = [
    ("What programming languages does Alice know?", ["Alice knows Python", "Alice is learning Rust"]),
    ("What is Bob's favorite food?", ["Bob loves pizza", "Bob prefers Italian cuisine"]),
    ("When did the project start?", ["Project started on January 1st", "Initial commit was in January"]),
    ("What are the team's goals?", ["Team goal: ship v2.0", "Objective: improve performance"]),
    ("Who works on the backend?", ["Alice works on backend", "Bob handles API development"]),
]

# Distractor memories (should not be retrieved)
DISTRACTOR_MEMORIES = [
    "The weather is nice today",
    "Coffee machine is broken",
    "Meeting scheduled for 3pm",
    "Printer needs paper",
    "Lunch menu has changed",
]


def create_test_memories(amos: Amos, tenant_id: str) -> List[Memory]:
    """Create test memories for benchmarking."""
    memories = []
    
    # Add relevant memories from test queries
    for query, relevant_contents in TEST_QUERIES:
        for content in relevant_contents:
            memory = amos.remember(
                tenant_id=tenant_id,
                content=content,
                type=MemoryType.FACT,
                importance=0.8,
                auto_process=False
            )
            memories.append(memory)
    
    # Add distractor memories
    for content in DISTRACTOR_MEMORIES:
        memory = amos.remember(
            tenant_id=tenant_id,
            content=content,
            type=MemoryType.OBSERVATION,
            importance=0.3,
            auto_process=False
        )
        memories.append(memory)
    
    return memories


def calculate_precision_recall(
    retrieved: List[Memory],
    expected_contents: List[str]
) -> Tuple[float, float]:
    """Calculate precision and recall for retrieved memories."""
    retrieved_contents = {m.content for m in retrieved}
    expected_set = set(expected_contents)
    
    true_positives = len(retrieved_contents & expected_set)
    
    precision = true_positives / len(retrieved_contents) if retrieved_contents else 0.0
    recall = true_positives / len(expected_set) if expected_set else 0.0
    
    return precision, recall


def benchmark_retrieval_quality(amos: Amos, tenant_id: str) -> dict:
    """Benchmark retrieval quality (precision/recall)."""
    print("\n📊 Benchmarking Retrieval Quality...")
    
    total_precision = 0.0
    total_recall = 0.0
    total_f1 = 0.0
    
    for query, expected_contents in TEST_QUERIES:
        results = amos.recall(tenant_id=tenant_id, query=query, limit=5)
        retrieved_memories = [r.memory for r in results]
        
        precision, recall = calculate_precision_recall(retrieved_memories, expected_contents)
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        total_precision += precision
        total_recall += recall
        total_f1 += f1
        
        print(f"  Query: '{query[:50]}...'")
        print(f"    Precision: {precision:.2f}, Recall: {recall:.2f}, F1: {f1:.2f}")
    
    num_queries = len(TEST_QUERIES)
    avg_precision = total_precision / num_queries
    avg_recall = total_recall / num_queries
    avg_f1 = total_f1 / num_queries
    
    return {
        "avg_precision": avg_precision,
        "avg_recall": avg_recall,
        "avg_f1": avg_f1
    }


def benchmark_latency(amos: Amos, tenant_id: str, num_iterations: int = 100) -> dict:
    """Benchmark query latency."""
    print(f"\n⚡ Benchmarking Latency ({num_iterations} iterations)...")
    
    query = "What programming languages does Alice know?"
    latencies = []
    
    for i in range(num_iterations):
        start = time.perf_counter()
        amos.recall(tenant_id=tenant_id, query=query, limit=10)
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # Convert to ms
    
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = sum(latencies) / len(latencies)
    
    print(f"  Average: {avg:.2f}ms")
    print(f"  P50: {p50:.2f}ms")
    print(f"  P95: {p95:.2f}ms")
    print(f"  P99: {p99:.2f}ms")
    
    return {
        "avg_ms": avg,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99
    }


def benchmark_embedding_overhead(amos: Amos, tenant_id: str) -> dict:
    """Benchmark embedding generation overhead."""
    print("\n🔢 Benchmarking Embedding Generation...")
    
    if not isinstance(amos.memories, PostgresStorage):
        print("  Skipped (not using PostgresStorage)")
        return {"skipped": True}
    
    # Measure time to create memory with embedding
    content = "This is a test memory for embedding benchmark"
    
    start = time.perf_counter()
    memory = amos.remember(
        tenant_id=tenant_id,
        content=content,
        type=MemoryType.OBSERVATION,
        auto_process=False
    )
    end = time.perf_counter()
    
    embedding_time_ms = (end - start) * 1000
    
    print(f"  Memory creation with embedding: {embedding_time_ms:.2f}ms")
    
    # Clean up
    amos.forget(tenant_id=tenant_id, memory_id=memory.id, force=True)
    
    return {
        "embedding_time_ms": embedding_time_ms
    }


def run_benchmark(storage_type: str, dsn: str = None) -> dict:
    """Run complete benchmark suite."""
    print(f"\n{'='*60}")
    print(f"🚀 Running Benchmark: {storage_type.upper()}")
    print(f"{'='*60}")
    
    # Create AMOS instance
    if storage_type == "memory":
        storage = InMemoryStorage()
    elif storage_type == "postgres":
        if not dsn:
            raise ValueError("PostgreSQL DSN required for postgres storage")
        storage = PostgresStorage(dsn)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")
    
    amos = Amos(memories=storage, timeline=storage, graph=storage, events=storage)
    tenant_id = f"benchmark-{storage_type}-{int(time.time())}"
    
    # Create test data
    print("\n📝 Creating test memories...")
    memories = create_test_memories(amos, tenant_id)
    print(f"  Created {len(memories)} memories")
    
    # Run benchmarks
    quality_results = benchmark_retrieval_quality(amos, tenant_id)
    latency_results = benchmark_latency(amos, tenant_id)
    embedding_results = benchmark_embedding_overhead(amos, tenant_id)
    
    # Cleanup
    print("\n🧹 Cleaning up...")
    for memory in memories:
        amos.forget(tenant_id=tenant_id, memory_id=memory.id, force=True)
    
    return {
        "storage_type": storage_type,
        "quality": quality_results,
        "latency": latency_results,
        "embedding": embedding_results
    }


def print_comparison(v1_results: dict, v2_results: dict):
    """Print comparison between V1 and V2."""
    print(f"\n{'='*60}")
    print("📈 V1 vs V2 Comparison")
    print(f"{'='*60}")
    
    print("\n🎯 Retrieval Quality:")
    print(f"  Precision: V1={v1_results['quality']['avg_precision']:.2f}, V2={v2_results['quality']['avg_precision']:.2f}")
    print(f"  Recall:    V1={v1_results['quality']['avg_recall']:.2f}, V2={v2_results['quality']['avg_recall']:.2f}")
    print(f"  F1 Score:  V1={v1_results['quality']['avg_f1']:.2f}, V2={v2_results['quality']['avg_f1']:.2f}")
    
    quality_improvement = (
        (v2_results['quality']['avg_f1'] - v1_results['quality']['avg_f1']) 
        / v1_results['quality']['avg_f1'] * 100
    )
    print(f"  → Quality improvement: {quality_improvement:+.1f}%")
    
    print("\n⚡ Latency:")
    print(f"  Average: V1={v1_results['latency']['avg_ms']:.2f}ms, V2={v2_results['latency']['avg_ms']:.2f}ms")
    print(f"  P95:     V1={v1_results['latency']['p95_ms']:.2f}ms, V2={v2_results['latency']['p95_ms']:.2f}ms")
    
    latency_overhead = (
        (v2_results['latency']['avg_ms'] - v1_results['latency']['avg_ms']) 
        / v1_results['latency']['avg_ms'] * 100
    )
    print(f"  → Latency overhead: {latency_overhead:+.1f}%")
    
    if not v2_results['embedding'].get('skipped'):
        print(f"\n🔢 Embedding Generation:")
        print(f"  Time: {v2_results['embedding']['embedding_time_ms']:.2f}ms")


def main():
    """Main benchmark entry point."""
    print("🔬 AMOS V2 Hybrid Retrieval Benchmark")
    print("=" * 60)
    
    # Check for PostgreSQL DSN
    postgres_dsn = os.getenv("AMOS_POSTGRES_DSN")
    
    # Run V1 benchmark (InMemoryStorage with lexical retrieval)
    v1_results = run_benchmark("memory")
    
    # Run V2 benchmark (PostgresStorage with hybrid retrieval)
    if postgres_dsn:
        v2_results = run_benchmark("postgres", postgres_dsn)
        print_comparison(v1_results, v2_results)
    else:
        print("\n⚠️  PostgreSQL DSN not set. Skipping V2 benchmark.")
        print("   Set AMOS_POSTGRES_DSN to run hybrid retrieval benchmark.")
    
    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    main()

# Made with Bob
