#!/usr/bin/env python3
"""Benchmark cascading extraction pipeline performance.

Tests the V2 cascading extraction pipeline against V1 regex extraction:
- Coverage: % of texts with extracted facts
- Latency: P50, P95, P99 extraction times
- Source distribution: Regex vs Fuzzy vs Tiny LLM vs Full LLM
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from amos.engines.pipeline import DeterministicMemoryPipeline


# Test dataset with various fact patterns
TEST_TEXTS = [
    # Simple patterns (should match regex)
    "Alice is building a new API",
    "Bob works on the frontend",
    "Charlie uses Python",
    "Diana prefers dark mode",
    
    # Fuzzy patterns (should match fuzzy)
    "Alice is a backend engineer",
    "Bob is skilled in Python",
    "Charlie loves pizza",
    "Diana is learning Rust",
    
    # Complex patterns (would need LLM)
    "Alice mentioned she's been working with microservices lately",
    "Bob said he's transitioning from Java to Go",
    "Charlie told me he's a big fan of Italian cuisine",
    "Diana expressed interest in functional programming",
    
    # Edge cases
    "The project deadline is next week",
    "We need to refactor the authentication module",
    "Performance optimization is critical",
    "The database migration failed",
]


def benchmark_v1_extraction():
    """Benchmark V1 regex-only extraction."""
    print("\n=== V1 Regex Extraction ===")
    
    pipeline = DeterministicMemoryPipeline(use_cascading=False)
    
    total_facts = 0
    texts_with_facts = 0
    latencies = []
    
    for text in TEST_TEXTS:
        start = time.perf_counter()
        facts = pipeline.extract_facts(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        latencies.append(latency_ms)
        total_facts += len(facts)
        if facts:
            texts_with_facts += 1
    
    # Calculate statistics
    coverage = texts_with_facts / len(TEST_TEXTS) * 100
    avg_latency = sum(latencies) / len(latencies)
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    
    print(f"Coverage: {coverage:.1f}% ({texts_with_facts}/{len(TEST_TEXTS)} texts)")
    print(f"Total facts: {total_facts}")
    print(f"Avg facts per text: {total_facts / len(TEST_TEXTS):.2f}")
    print(f"Latency - Avg: {avg_latency:.2f}ms, P50: {p50:.2f}ms, P95: {p95:.2f}ms, P99: {p99:.2f}ms")
    
    return {
        "coverage": coverage,
        "total_facts": total_facts,
        "avg_latency": avg_latency,
        "p50": p50,
        "p95": p95,
        "p99": p99,
    }


def benchmark_v2_extraction(use_tiny_llm: bool = False):
    """Benchmark V2 cascading extraction."""
    print(f"\n=== V2 Cascading Extraction (Tiny LLM: {use_tiny_llm}) ===")
    
    pipeline = DeterministicMemoryPipeline(use_cascading=True, use_tiny_llm=use_tiny_llm)
    
    total_facts = 0
    texts_with_facts = 0
    latencies = []
    source_counts = {"regex": 0, "fuzzy": 0, "tiny_llm": 0, "full_llm": 0}
    
    for text in TEST_TEXTS:
        start = time.perf_counter()
        facts = pipeline.extract_facts(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        latencies.append(latency_ms)
        total_facts += len(facts)
        if facts:
            texts_with_facts += 1
            
        # Count by source (facts have confidence attribute, not source in FactCandidate)
        # We'll need to track this differently
    
    # Calculate statistics
    coverage = texts_with_facts / len(TEST_TEXTS) * 100
    avg_latency = sum(latencies) / len(latencies)
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    
    print(f"Coverage: {coverage:.1f}% ({texts_with_facts}/{len(TEST_TEXTS)} texts)")
    print(f"Total facts: {total_facts}")
    print(f"Avg facts per text: {total_facts / len(TEST_TEXTS):.2f}")
    print(f"Latency - Avg: {avg_latency:.2f}ms, P50: {p50:.2f}ms, P95: {p95:.2f}ms, P99: {p99:.2f}ms")
    
    return {
        "coverage": coverage,
        "total_facts": total_facts,
        "avg_latency": avg_latency,
        "p50": p50,
        "p95": p95,
        "p99": p99,
    }


def test_extraction_sources():
    """Test extraction source distribution."""
    print("\n=== Extraction Source Distribution ===")
    
    from amos.engines.extraction import CascadingExtractor
    
    extractor = CascadingExtractor(use_tiny_llm=False, use_full_llm=False)
    
    source_counts = {"regex": 0, "fuzzy": 0, "tiny_llm": 0, "full_llm": 0, "none": 0}
    
    for text in TEST_TEXTS:
        facts = extractor.extract(text)
        if not facts:
            source_counts["none"] += 1
        else:
            for fact in facts:
                source_counts[fact.source.value] += 1
    
    print(f"Regex: {source_counts['regex']}")
    print(f"Fuzzy: {source_counts['fuzzy']}")
    print(f"Tiny LLM: {source_counts['tiny_llm']}")
    print(f"Full LLM: {source_counts['full_llm']}")
    print(f"No extraction: {source_counts['none']}")
    
    total_extractions = sum(source_counts.values()) - source_counts['none']
    if total_extractions > 0:
        print(f"\nDistribution:")
        print(f"  Regex: {source_counts['regex'] / total_extractions * 100:.1f}%")
        print(f"  Fuzzy: {source_counts['fuzzy'] / total_extractions * 100:.1f}%")
        print(f"  Tiny LLM: {source_counts['tiny_llm'] / total_extractions * 100:.1f}%")
        print(f"  Full LLM: {source_counts['full_llm'] / total_extractions * 100:.1f}%")


def main():
    """Run extraction benchmarks."""
    print("=" * 60)
    print("AMOS V2 Cascading Extraction Benchmark")
    print("=" * 60)
    
    # Test extraction sources
    test_extraction_sources()
    
    # Benchmark V1
    v1_results = benchmark_v1_extraction()
    
    # Benchmark V2 without tiny LLM
    v2_results = benchmark_v2_extraction(use_tiny_llm=False)
    
    # Compare results
    print("\n=== Comparison ===")
    print(f"Coverage improvement: {v2_results['coverage'] - v1_results['coverage']:+.1f}%")
    print(f"Facts improvement: {v2_results['total_facts'] - v1_results['total_facts']:+d}")
    print(f"Latency change: {v2_results['avg_latency'] - v1_results['avg_latency']:+.2f}ms")
    
    # Summary
    print("\n=== Summary ===")
    print(f"✓ V2 cascading extraction implemented")
    print(f"✓ Coverage: {v2_results['coverage']:.1f}% (target: >80%)")
    print(f"✓ Latency P95: {v2_results['p95']:.2f}ms (target: <100ms)")
    
    if v2_results['coverage'] >= 80 and v2_results['p95'] < 100:
        print("\n✅ Phase 2 targets achieved!")
    else:
        print("\n⚠️  Phase 2 targets not yet met")
        if v2_results['coverage'] < 80:
            print(f"   - Coverage below target: {v2_results['coverage']:.1f}% < 80%")
        if v2_results['p95'] >= 100:
            print(f"   - Latency above target: {v2_results['p95']:.2f}ms >= 100ms")


if __name__ == "__main__":
    main()

# Made with Bob
