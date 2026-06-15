#!/usr/bin/env python3
"""
30-Day Long-Term Memory Lifecycle Test with Time Mocking

Tests memory lifecycle over an extended period with:
1. Mocked time passage (simulates 30 real days)
2. Extreme access patterns (hot vs cold memories)
3. Natural lifecycle progression with heat decay
4. Tier transition validation
5. GC effectiveness measurement

Simulates 30 days by manually advancing memory timestamps.
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from collections import defaultdict
import random

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from amos.runtime import build_amos
from amos.models import MemoryType


class LongTerm30DayTest:
    """30-day long-term lifecycle test."""
    
    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path).expanduser()
        self.amos = None
        self.tenant_id = "longterm_test_user"
        
        # Simulated time starts at test beginning
        self.simulated_now = datetime.now(timezone.utc)
        self.test_start_time = self.simulated_now
        
        # Track memory IDs by category
        self.hot_memories = []  # Frequently accessed
        self.warm_memories = []  # Occasionally accessed
        self.cold_memories = []  # Rarely accessed
        
        self.results = {
            "test_start": self.simulated_now.isoformat(),
            "test_duration_days": 30,
            "daily_snapshots": [],
            "tier_transitions": [],
            "final_distribution": {},
            "gc_summary": {
                "total_runs": 0,
                "total_archived": 0,
                "total_deleted": 0
            }
        }
    
    def load_dataset(self, max_conversations: int = 3) -> List[Dict]:
        """Load LoCoMo dataset."""
        print(f"📁 Loading dataset from: {self.dataset_path}")
        
        with open(self.dataset_path, 'r') as f:
            data = json.load(f)
        
        conversations = data[:max_conversations]
        print(f"✓ Loaded {len(conversations)} conversations")
        return conversations
    
    def store_initial_memories(self, conversations: List[Dict]) -> int:
        """Store all conversations and categorize memories."""
        print("\n" + "="*70)
        print("PHASE 1: Storing Initial Memories")
        print("="*70)
        
        all_memory_ids = []
        total_memories = 0
        
        for conv_idx, conversation in enumerate(conversations):
            sample_id = conversation.get('sample_id', f'conv_{conv_idx}')
            conv_data = conversation.get('conversation', {})
            
            # Find all sessions
            session_keys = sorted([k for k in conv_data.keys() 
                                 if k.startswith('session_') and not k.endswith('_date_time')])
            
            print(f"\nConversation {conv_idx + 1}: {sample_id} ({len(session_keys)} sessions)")
            
            for session_key in session_keys:
                session_data = conv_data.get(session_key, [])
                
                for turn in session_data:
                    text = turn.get('text', '').strip()
                    if not text:
                        continue
                    
                    # Store memory
                    memory = self.amos.remember(
                        tenant_id=self.tenant_id,
                        content=text,
                        type=MemoryType.OBSERVATION,
                        metadata={
                            'sample_id': sample_id,
                            'session': session_key,
                            'speaker': turn.get('speaker', 'unknown')
                        },
                        auto_process=True
                    )
                    
                    all_memory_ids.append(memory.id)
                    total_memories += 1
                
                if total_memories % 100 == 0:
                    print(f"  Stored {total_memories} memories...")
        
        print(f"\n✓ Stored {total_memories} total memories")
        
        # Categorize memories for access patterns
        random.shuffle(all_memory_ids)
        split1 = len(all_memory_ids) // 10  # 10% hot
        split2 = len(all_memory_ids) // 2   # 40% warm, 50% cold
        
        self.hot_memories = all_memory_ids[:split1]
        self.warm_memories = all_memory_ids[split1:split2]
        self.cold_memories = all_memory_ids[split2:]
        
        print(f"\nMemory categorization:")
        print(f"  Hot (10%): {len(self.hot_memories)} memories")
        print(f"  Warm (40%): {len(self.warm_memories)} memories")
        print(f"  Cold (50%): {len(self.cold_memories)} memories")
        
        return total_memories
    
    def age_all_memories_by_one_day(self):
        """Age all memories by moving their timestamps back 1 day.
        
        This simulates time passage without actually waiting.
        We age ALL memories (not just unaccessed ones) to keep timestamps consistent.
        """
        one_day = timedelta(days=1)
        
        # Batch update all memories
        memories_to_update = []
        for memory in self.amos.memories.list(self.tenant_id):
            # Move all timestamps back by 1 day
            memory.created_at = memory.created_at - one_day
            memory.updated_at = memory.updated_at - one_day
            if memory.accessed_at:
                memory.accessed_at = memory.accessed_at - one_day
            memories_to_update.append(memory)
        
        # Batch save (more efficient)
        for memory in memories_to_update:
            self.amos.memories.put(memory)
    
    
    def simulate_day(self, day: int):
        """Simulate one day of activity with time mocking."""
        print(f"\n{'='*70}")
        print(f"Day {day}/30")
        print(f"{'='*70}")
        
        # Advance simulated time by 1 day
        self.simulated_now += timedelta(days=1)
        
        # Age all memories that weren't accessed (simulates time passage)
        self.age_all_memories_by_one_day()
        
        # Access patterns change over time
        if day <= 7:
            # Week 1: High activity
            hot_access_prob = 0.9
            warm_access_prob = 0.5
            cold_access_prob = 0.1
        elif day <= 14:
            # Week 2: Medium activity
            hot_access_prob = 0.7
            warm_access_prob = 0.3
            cold_access_prob = 0.05
        elif day <= 21:
            # Week 3: Low activity
            hot_access_prob = 0.5
            warm_access_prob = 0.2
            cold_access_prob = 0.02
        else:
            # Week 4: Very low activity
            hot_access_prob = 0.3
            warm_access_prob = 0.1
            cold_access_prob = 0.01
        
        # Simulate accesses
        hot_accessed = sum(1 for _ in self.hot_memories if random.random() < hot_access_prob)
        warm_accessed = sum(1 for _ in self.warm_memories if random.random() < warm_access_prob)
        cold_accessed = sum(1 for _ in self.cold_memories if random.random() < cold_access_prob)
        
        total_accessed = hot_accessed + warm_accessed + cold_accessed
        
        print(f"  Accesses: {total_accessed} total")
        print(f"    Hot: {hot_accessed}/{len(self.hot_memories)} ({hot_accessed/len(self.hot_memories)*100:.1f}%)")
        print(f"    Warm: {warm_accessed}/{len(self.warm_memories)} ({warm_accessed/len(self.warm_memories)*100:.1f}%)")
        print(f"    Cold: {cold_accessed}/{len(self.cold_memories)} ({cold_accessed/len(self.cold_memories)*100:.1f}%)")
        
        # Simulate actual accesses (query memories)
        accessed_ids = []
        accessed_ids.extend(random.sample(self.hot_memories, hot_accessed))
        accessed_ids.extend(random.sample(self.warm_memories, warm_accessed))
        if cold_accessed > 0:
            accessed_ids.extend(random.sample(self.cold_memories, min(cold_accessed, len(self.cold_memories))))
        
        # Update accessed_at for accessed memories (simulates access with current simulated time)
        for memory_id in accessed_ids:
            try:
                memory = self.amos.memories.get(memory_id)
                if memory:
                    memory.accessed_at = self.simulated_now
                    memory.retrieval_count += 1
                    self.amos.memories.put(memory)
            except:
                pass
        
        # Run promotion check every 3 days
        if day % 3 == 0:
            print(f"  Running promotion check...")
            promo_report = self.amos.run_promotion_check(tenant_id=self.tenant_id, simulated_now=self.simulated_now)
            print(f"    Promoted: {promo_report['summary']['promoted_count']}")
            print(f"    Demoted: {promo_report['summary']['demoted_count']}")
            
            # Track transitions
            for promoted in promo_report['promoted']:
                self.results['tier_transitions'].append({
                    'day': day,
                    'type': 'promotion',
                    'memory_id': promoted['memory_id'],
                    'from_tier': promoted['from_tier'],
                    'to_tier': promoted['to_tier'],
                    'heat': promoted['heat_score'],
                    'survivor_count': promoted['survivor_count']
                })
        
        # Run GC every 7 days
        if day % 7 == 0:
            print(f"  Running garbage collection...")
            gc_report = self.amos.run_gc(tenant_id=self.tenant_id, simulated_now=self.simulated_now)
            print(f"    Archived: {gc_report['summary']['archived_count']}")
            print(f"    Deleted: {gc_report['summary']['deleted_count']}")
            
            self.results['gc_summary']['total_runs'] += 1
            self.results['gc_summary']['total_archived'] += gc_report['summary']['archived_count']
            self.results['gc_summary']['total_deleted'] += gc_report['summary']['deleted_count']
        
        # Take daily snapshot
        tier_dist = self.amos.get_tier_distribution(tenant_id=self.tenant_id)
        heat_dist = self.amos.get_heat_distribution(tenant_id=self.tenant_id, simulated_now=self.simulated_now)
        
        snapshot = {
            'day': day,
            'tier_distribution': tier_dist,
            'heat_stats': heat_dist['stats'],
            'accesses': total_accessed
        }
        self.results['daily_snapshots'].append(snapshot)
        
        print(f"  Tier distribution: {tier_dist}")
        print(f"  Heat: mean={heat_dist['stats']['mean']:.3f}, "
              f"hot={heat_dist['stats']['hot_count']}, "
              f"cold={heat_dist['stats']['cold_count']}")
    
    def run(self, max_conversations: int = 3):
        """Run the 30-day test."""
        print("="*70)
        print("30-DAY LONG-TERM MEMORY LIFECYCLE TEST")
        print("="*70)
        
        # Load dataset
        conversations = self.load_dataset(max_conversations)
        
        # Initialize AMOS
        print(f"\n🚀 Initializing AMOS...")
        self.amos = build_amos()
        print(f"✓ AMOS initialized")
        
        # Store initial memories
        total_memories = self.store_initial_memories(conversations)
        
        # Simulate 30 days
        print("\n" + "="*70)
        print("PHASE 2: Simulating 30 Days of Activity")
        print("="*70)
        
        start_time = time.time()
        
        for day in range(1, 31):
            self.simulate_day(day)
            
            # Progress update
            if day % 5 == 0:
                elapsed = time.time() - start_time
                print(f"\n  Progress: {day}/30 days ({day/30*100:.0f}%) - {elapsed:.1f}s elapsed")
        
        # Final analysis
        print("\n" + "="*70)
        print("PHASE 3: Final Analysis")
        print("="*70)
        
        final_tier_dist = self.amos.get_tier_distribution(tenant_id=self.tenant_id)
        final_heat_dist = self.amos.get_heat_distribution(tenant_id=self.tenant_id, simulated_now=self.simulated_now)
        
        self.results['final_distribution'] = {
            'tiers': final_tier_dist,
            'heat': final_heat_dist['stats']
        }
        
        print(f"\nFinal tier distribution:")
        for tier, count in final_tier_dist.items():
            pct = count / total_memories * 100
            print(f"  {tier}: {count} ({pct:.1f}%)")
        
        print(f"\nFinal heat distribution:")
        print(f"  Hot (>0.7): {final_heat_dist['stats']['hot_count']}")
        print(f"  Warm (0.3-0.7): {final_heat_dist['stats']['warm_count']}")
        print(f"  Cold (<0.3): {final_heat_dist['stats']['cold_count']}")
        print(f"  Mean: {final_heat_dist['stats']['mean']:.3f}")
        
        print(f"\nLifecycle transitions:")
        print(f"  Total transitions: {len(self.results['tier_transitions'])}")
        print(f"  Promotions: {sum(1 for t in self.results['tier_transitions'] if t['type'] == 'promotion')}")
        
        print(f"\nGarbage collection:")
        print(f"  Total runs: {self.results['gc_summary']['total_runs']}")
        print(f"  Total archived: {self.results['gc_summary']['total_archived']}")
        print(f"  Total deleted: {self.results['gc_summary']['total_deleted']}")
        
        # Save results
        self.save_results()
    
    def save_results(self):
        """Save results to file."""
        output_dir = Path("benchmark-results")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_file = output_dir / f"long-term-30day-{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {output_file}")


def main():
    """Main entry point."""
    import sys
    
    dataset_path = "~/Downloads/locomo10.json"
    max_conversations = 2  # Use 2 conversations for faster testing
    
    if len(sys.argv) > 1:
        max_conversations = int(sys.argv[1])
    
    print("="*70)
    print("30-DAY LONG-TERM MEMORY LIFECYCLE TEST")
    print("="*70)
    print(f"\nDataset: {dataset_path}")
    print(f"Conversations: {max_conversations}")
    print(f"Duration: 30 simulated days")
    print("\nThis test will:")
    print("  1. Store memories from conversations")
    print("  2. Simulate 30 days of varying access patterns")
    print("  3. Track tier transitions over time")
    print("  4. Run GC every 7 days")
    print("  5. Analyze lifecycle effectiveness")
    print("\nStarting test...\n")
    
    test = LongTerm30DayTest(dataset_path)
    test.run(max_conversations=max_conversations)
    
    print("\n✅ 30-day long-term test complete!")


if __name__ == "__main__":
    main()

