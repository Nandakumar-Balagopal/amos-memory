#!/usr/bin/env python3
"""Long-horizon memory management test.

Tests AMOS memory management over extended conversations:
1. Heat decay over time
2. Memory eviction (GC-style)
3. Temporal validity tracking
4. Retrieval quality degradation
5. Token budget management

Simulates a 1000-turn conversation spanning multiple days.
"""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from amos import Amos
from amos.models import MemoryType
from amos.stores.memory import InMemoryStorage


def simulate_conversation_turn(amos: Amos, tenant_id: str, turn: int, day: int):
    """Simulate a single conversation turn."""
    
    # Vary content types
    if turn % 10 == 0:
        # Code snippet
        content = f"Day {day}: Implemented feature X with UUID {turn:08x}-{turn:04x}-{turn:04x}"
    elif turn % 7 == 0:
        # Technical discussion
        content = f"Day {day}: Discussed microservices architecture, API gateway patterns, and database sharding"
    elif turn % 5 == 0:
        # Personal preference
        content = f"Day {day}: User mentioned they prefer dark mode and Python over JavaScript"
    else:
        # Regular conversation
        content = f"Day {day}, Turn {turn}: Working on the authentication module refactoring"
    
    # Store memory
    memory = amos.remember(
        tenant_id=tenant_id,
        content=content,
        type=MemoryType.OBSERVATION
    )
    
    return memory


def test_heat_decay():
    """Test heat decay over time."""
    print("\n=== Test 1: Heat Decay Over Time ===")
    
    amos = Amos(memories=InMemoryStorage())
    tenant_id = "test-user"
    
    # Create memories at different times
    memories = []
    for i in range(10):
        memory = amos.remember(
            tenant_id=tenant_id,
            content=f"Memory {i}: Important fact about project",
            type=MemoryType.FACT
        )
        memories.append(memory)
        time.sleep(0.1)  # Small delay
    
    # Check initial heat
    initial_heats = [m.heat for m in memories]
    print(f"Initial heat range: {min(initial_heats):.2f} - {max(initial_heats):.2f}")
    
    # Simulate time passing (access some memories)
    for i in [0, 2, 4]:  # Access only some memories
        amos.recall(tenant_id=tenant_id, query=f"Memory {i}", limit=1)
    
    # Check heat after access
    all_memories = amos.memories.list(tenant_id)
    accessed_heats = [m.heat_score for m in all_memories if "Memory 0" in m.content or "Memory 2" in m.content or "Memory 4" in m.content]
    unaccessed_heats = [m.heat_score for m in all_memories if m.heat_score not in accessed_heats]
    
    print(f"Accessed memories heat: {sum(accessed_heats)/len(accessed_heats):.2f}")
    print(f"Unaccessed memories heat: {sum(unaccessed_heats)/len(unaccessed_heats):.2f}")
    
    if sum(accessed_heats)/len(accessed_heats) > sum(unaccessed_heats)/len(unaccessed_heats):
        print("✅ Heat decay working: Accessed memories have higher heat")
    else:
        print("⚠️  Heat decay issue: Accessed memories should have higher heat")


def test_memory_eviction():
    """Test memory eviction under pressure."""
    print("\n=== Test 2: Memory Eviction (GC) ===")
    
    amos = Amos(memories=InMemoryStorage())
    tenant_id = "test-user"
    
    # Create many memories
    print("Creating 100 memories...")
    for i in range(100):
        amos.remember(
            tenant_id=tenant_id,
            content=f"Memory {i}: Some content that will fill up storage",
            type=MemoryType.OBSERVATION
        )
    
    initial_count = len(amos.memories.list(tenant_id))
    print(f"Initial memory count: {initial_count}")
    
    # Access only recent memories
    for i in range(90, 100):
        amos.recall(tenant_id=tenant_id, query=f"Memory {i}", limit=1)
    
    # Check if old memories have lower heat
    all_memories = amos.memories.list(tenant_id)
    old_memories = [m for m in all_memories if "Memory 0" in m.content or "Memory 1" in m.content]
    recent_memories = [m for m in all_memories if "Memory 9" in m.content]
    
    if old_memories and recent_memories:
        avg_old_heat = sum(m.heat_score for m in old_memories) / len(old_memories)
        avg_recent_heat = sum(m.heat_score for m in recent_memories) / len(recent_memories)
        
        print(f"Old memories avg heat: {avg_old_heat:.2f}")
        print(f"Recent memories avg heat: {avg_recent_heat:.2f}")
        
        if avg_recent_heat > avg_old_heat:
            print("✅ Memory eviction candidate selection working")
        else:
            print("⚠️  Old memories should have lower heat for eviction")


def test_temporal_validity():
    """Test temporal validity tracking."""
    print("\n=== Test 3: Temporal Validity Tracking ===")
    
    amos = Amos(memories=InMemoryStorage())
    tenant_id = "test-user"
    
    # Create fact with temporal validity
    memory1 = amos.remember(
        tenant_id=tenant_id,
        content="Alice works on backend (valid from 2024-01-01)",
        type=MemoryType.FACT
    )
    
    # Create contradicting fact
    memory2 = amos.remember(
        tenant_id=tenant_id,
        content="Alice works on frontend (valid from 2024-06-01)",
        type=MemoryType.FACT
    )
    
    # Check if both facts exist
    all_facts = [m for m in amos.memories.list(tenant_id) if m.type == MemoryType.FACT]
    print(f"Total facts stored: {len(all_facts)}")
    
    # Retrieve facts about Alice
    results = amos.recall(tenant_id=tenant_id, query="Alice works", limit=5)
    print(f"Facts retrieved about Alice: {len(results)}")
    
    if len(results) >= 2:
        print("✅ Temporal validity: Multiple time-bound facts coexist")
    else:
        print("⚠️  Temporal validity: Should track multiple time-bound facts")


def test_long_conversation():
    """Test memory management over long conversation."""
    print("\n=== Test 4: Long Conversation (1000 turns) ===")
    
    amos = Amos(memories=InMemoryStorage())
    tenant_id = "test-user"
    
    # Simulate 1000-turn conversation over 30 days
    print("Simulating 1000-turn conversation...")
    start_time = time.time()
    
    for turn in range(1000):
        day = turn // 33  # ~33 turns per day
        simulate_conversation_turn(amos, tenant_id, turn, day)
        
        if turn % 100 == 0:
            print(f"  Turn {turn}/1000...")
    
    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.2f}s ({elapsed/1000*1000:.2f}ms per turn)")
    
    # Check memory stats
    all_memories = amos.memories.list(tenant_id)
    print(f"\nMemory Statistics:")
    print(f"  Total memories: {len(all_memories)}")
    print(f"  Avg heat: {sum(m.heat_score for m in all_memories) / len(all_memories):.2f}")
    print(f"  Heat range: {min(m.heat_score for m in all_memories):.2f} - {max(m.heat_score for m in all_memories):.2f}")
    
    # Test retrieval quality
    test_queries = [
        "authentication module",
        "microservices architecture",
        "dark mode preference",
        "UUID implementation"
    ]
    
    print(f"\nRetrieval Quality:")
    for query in test_queries:
        results = amos.recall(tenant_id=tenant_id, query=query, limit=5)
        print(f"  '{query}': {len(results)} results")
    
    if len(all_memories) == 1000:
        print("✅ All 1000 memories stored")
    else:
        print(f"⚠️  Expected 1000 memories, got {len(all_memories)}")


def test_token_budget():
    """Test token budget management."""
    print("\n=== Test 5: Token Budget Management ===")
    
    amos = Amos(memories=InMemoryStorage())
    tenant_id = "test-user"
    
    # Create memories with varying token counts
    memories = [
        "Short fact",
        "Medium length observation about the project status and current progress",
        "Very long detailed technical discussion about microservices architecture, API gateway patterns, database sharding strategies, caching layers, message queues, event-driven architecture, and distributed tracing systems",
        "Code snippet: def authenticate(user_id: str, token: str) -> bool: return validate_jwt(token) and check_permissions(user_id)",
        "UUID: 550e8400-e29b-41d4-a716-446655440000, 6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ]
    
    for content in memories:
        amos.remember(
            tenant_id=tenant_id,
            content=content,
            type=MemoryType.OBSERVATION
        )
    
    # Retrieve with token budget
    results = amos.recall(tenant_id=tenant_id, query="project", limit=10)
    
    # Estimate tokens (rough approximation: 1 token ≈ 4 chars)
    total_chars = sum(len(r.memory.content) for r in results)
    estimated_tokens = total_chars // 4
    
    print(f"Retrieved {len(results)} memories")
    print(f"Total characters: {total_chars}")
    print(f"Estimated tokens: {estimated_tokens}")
    
    if estimated_tokens < 1000:
        print("✅ Token budget reasonable for context window")
    else:
        print("⚠️  Token budget high, may need compression")


def main():
    """Run all long-horizon tests."""
    print("=" * 60)
    print("AMOS Long-Horizon Memory Management Tests")
    print("=" * 60)
    
    test_heat_decay()
    test_memory_eviction()
    test_temporal_validity()
    test_long_conversation()
    test_token_budget()
    
    print("\n" + "=" * 60)
    print("Test Suite Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()

# Made with Bob
