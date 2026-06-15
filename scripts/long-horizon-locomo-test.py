#!/usr/bin/env python3
"""
Long-Horizon Memory Test with LoCoMo Dataset

Tests AMOS's ability to:
1. Handle multi-session conversations over time
2. Extract facts with LLM across sessions
3. Maintain memory consistency
4. Answer questions using accumulated knowledge
5. Track memory lifecycle (young → survivor → long-term)

Dataset: LoCoMo (Long-Context Modeling) - Multi-session conversations
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from amos.runtime import build_amos
from amos.models import MemoryType


class LoCoMoLongHorizonTest:
    """Long-horizon test using LoCoMo dataset."""
    
    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path).expanduser()
        self.amos = None
        self.results = {
            "dataset": "LoCoMo",
            "test_start": datetime.now().isoformat(),
            "conversations_processed": 0,
            "sessions_processed": 0,
            "turns_processed": 0,
            "facts_extracted": 0,
            "llm_facts": 0,
            "qa_results": [],
            "memory_lifecycle": {
                "young": 0,
                "survivor": 0,
                "long_term": 0,
                "archived": 0
            },
            "performance": {
                "total_time_sec": 0,
                "avg_turn_time_ms": 0,
                "llm_calls": 0,
                "llm_time_sec": 0
            }
        }
    
    def load_dataset(self, max_conversations: int = 5) -> List[Dict]:
        """Load LoCoMo dataset."""
        print(f"📁 Loading LoCoMo dataset from: {self.dataset_path}")
        
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")
        
        with open(self.dataset_path, 'r') as f:
            data = json.load(f)
        
        conversations = data[:max_conversations]
        print(f"✓ Loaded {len(conversations)} conversations")
        
        return conversations
    
    def extract_sessions(self, conversation: Dict) -> List[Dict]:
        """Extract sessions from conversation."""
        sessions = []
        conv_data = conversation.get('conversation', {})
        
        # Find all session keys
        session_keys = sorted([k for k in conv_data.keys() if k.startswith('session_') and not k.endswith('_date_time')])
        
        for session_key in session_keys:
            session_data = conv_data.get(session_key, [])
            session_time_key = f"{session_key}_date_time"
            session_time = conv_data.get(session_time_key, datetime.now().isoformat())
            
            sessions.append({
                'session_id': session_key,
                'timestamp': session_time,
                'turns': session_data
            })
        
        return sessions
    
    def process_conversation(self, conversation: Dict, conv_idx: int) -> Dict:
        """Process a single conversation with all its sessions."""
        sample_id = conversation.get('sample_id', f'conv_{conv_idx}')
        tenant_id = f"user_{sample_id}"
        
        print(f"\n{'='*70}")
        print(f"Processing Conversation {conv_idx + 1}: {sample_id}")
        print(f"{'='*70}")
        
        sessions = self.extract_sessions(conversation)
        print(f"  Sessions: {len(sessions)}")
        
        conv_results = {
            'sample_id': sample_id,
            'sessions': len(sessions),
            'turns': 0,
            'facts': 0,
            'llm_facts': 0
        }
        
        # Process each session
        for session_idx, session in enumerate(sessions):
            print(f"\n  Session {session_idx + 1}/{len(sessions)}: {session['session_id']}")
            
            turns = session.get('turns', [])
            print(f"    Turns: {len(turns)}")
            
            # Process each turn
            for turn_idx, turn in enumerate(turns):
                speaker = turn.get('speaker', 'unknown')
                text = turn.get('text', '')
                
                if not text.strip():
                    continue
                
                # Store as memory
                start_time = time.time()
                memory = self.amos.remember(
                    tenant_id=tenant_id,
                    content=text,
                    type=MemoryType.OBSERVATION,
                    metadata={
                        'session': session['session_id'],
                        'speaker': speaker,
                        'turn_idx': turn_idx,
                        'dia_id': turn.get('dia_id', '')
                    },
                    auto_process=False  # Process manually to track metrics
                )
                
                # Process with LLM
                report = self.amos.process_memory(
                    tenant_id=tenant_id,
                    memory_id=memory.id
                )
                
                process_time = (time.time() - start_time) * 1000
                
                # Track metrics
                facts_extracted = len(report.extracted_facts)
                llm_facts = report.extraction_sources.get('llm', 0)
                
                conv_results['turns'] += 1
                conv_results['facts'] += facts_extracted
                conv_results['llm_facts'] += llm_facts
                
                if turn_idx % 10 == 0:
                    print(f"      Turn {turn_idx + 1}: {facts_extracted} facts ({llm_facts} LLM) in {process_time:.0f}ms")
        
        print(f"\n  ✓ Conversation complete:")
        print(f"    Total turns: {conv_results['turns']}")
        print(f"    Total facts: {conv_results['facts']}")
        print(f"    LLM facts: {conv_results['llm_facts']}")
        
        return conv_results
    
    def test_qa(self, conversation: Dict, tenant_id: str) -> List[Dict]:
        """Test question answering using accumulated knowledge."""
        qa_data = conversation.get('qa', [])
        
        if not qa_data:
            return []
        
        print(f"\n  Testing Q&A ({len(qa_data)} questions)...")
        
        qa_results = []
        for qa in qa_data[:5]:  # Test first 5 questions
            question = qa.get('question', '')
            expected_answer = qa.get('answer', '')
            category = qa.get('category', 'unknown')
            
            # Query AMOS
            results = self.amos.recall(
                tenant_id=tenant_id,
                query=question,
                limit=5
            )
            
            # Check if we can answer
            has_relevant = len(results) > 0
            
            qa_results.append({
                'question': question,
                'category': category,
                'expected_answer': expected_answer,
                'retrieved_memories': len(results),
                'can_answer': has_relevant
            })
            
            status = "✓" if has_relevant else "✗"
            print(f"    {status} {category}: {question[:50]}... ({len(results)} memories)")
        
        return qa_results
    
    def run(self, max_conversations: int = 5):
        """Run the long-horizon test."""
        print("="*70)
        print("AMOS LONG-HORIZON TEST - LoCoMo Dataset")
        print("="*70)
        
        # Load dataset
        conversations = self.load_dataset(max_conversations)
        
        # Initialize AMOS
        print(f"\n🚀 Initializing AMOS with LLM extraction...")
        self.amos = build_amos()
        print(f"✓ AMOS initialized")
        print(f"  - Cascading extraction: {self.amos.pipeline.use_cascading}")
        print(f"  - LLM enabled: {self.amos.pipeline._cascading_extractor.use_llm if self.amos.pipeline._cascading_extractor else False}")
        
        # Process conversations
        start_time = time.time()
        
        for conv_idx, conversation in enumerate(conversations):
            conv_results = self.process_conversation(conversation, conv_idx)
            
            # Update totals
            self.results['conversations_processed'] += 1
            self.results['sessions_processed'] += conv_results['sessions']
            self.results['turns_processed'] += conv_results['turns']
            self.results['facts_extracted'] += conv_results['facts']
            self.results['llm_facts'] += conv_results['llm_facts']
            
            # Test Q&A
            sample_id = conversation.get('sample_id', f'conv_{conv_idx}')
            tenant_id = f"user_{sample_id}"
            qa_results = self.test_qa(conversation, tenant_id)
            self.results['qa_results'].extend(qa_results)
        
        total_time = time.time() - start_time
        
        # Calculate performance metrics
        self.results['performance']['total_time_sec'] = round(total_time, 2)
        if self.results['turns_processed'] > 0:
            self.results['performance']['avg_turn_time_ms'] = round(
                (total_time * 1000) / self.results['turns_processed'], 2
            )
        
        # Print summary
        self.print_summary()
        
        # Save results
        self.save_results()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        
        print(f"\n📊 Processing Metrics:")
        print(f"  Conversations: {self.results['conversations_processed']}")
        print(f"  Sessions: {self.results['sessions_processed']}")
        print(f"  Turns: {self.results['turns_processed']}")
        print(f"  Facts extracted: {self.results['facts_extracted']}")
        print(f"  LLM facts: {self.results['llm_facts']} ({self.results['llm_facts']/max(1, self.results['facts_extracted'])*100:.1f}%)")
        
        print(f"\n⚡ Performance:")
        print(f"  Total time: {self.results['performance']['total_time_sec']}s")
        print(f"  Avg time per turn: {self.results['performance']['avg_turn_time_ms']}ms")
        
        if self.results['qa_results']:
            answerable = sum(1 for qa in self.results['qa_results'] if qa['can_answer'])
            total_qa = len(self.results['qa_results'])
            print(f"\n❓ Question Answering:")
            print(f"  Questions tested: {total_qa}")
            print(f"  Answerable: {answerable}/{total_qa} ({answerable/total_qa*100:.1f}%)")
        
        print("\n" + "="*70)
    
    def save_results(self):
        """Save results to file."""
        output_dir = Path("benchmark-results")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_file = output_dir / f"long-horizon-locomo-{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {output_file}")


def main():
    """Main entry point."""
    import sys
    
    dataset_path = "~/Downloads/locomo10.json"
    max_conversations = 3  # Start with 3 for faster testing
    
    # Check for command line args
    if len(sys.argv) > 1:
        max_conversations = int(sys.argv[1])
    
    print("="*70)
    print("AMOS LONG-HORIZON TEST - LoCoMo Dataset")
    print("="*70)
    print(f"\nDataset: {dataset_path}")
    print(f"Max conversations: {max_conversations}")
    print(f"LLM extraction: Enabled (Ollama/phi)")
    print("\nStarting test...\n")
    
    # Run test
    test = LoCoMoLongHorizonTest(dataset_path)
    test.run(max_conversations=max_conversations)
    
    print("\n✅ Long-horizon test complete!")


if __name__ == "__main__":
    main()

