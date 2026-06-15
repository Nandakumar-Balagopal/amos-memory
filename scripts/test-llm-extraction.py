#!/usr/bin/env python3
"""
Quick test to verify LLM extraction is working.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from amos.runtime import build_amos

def main():
    print("=" * 60)
    print("Testing LLM Extraction")
    print("=" * 60)
    
    # Build AMOS with LLM enabled
    print("\n1. Building AMOS with LLM extraction enabled...")
    amos = build_amos()
    
    print(f"   - use_cascading: {amos.pipeline.use_cascading}")
    print(f"   - use_tiny_llm: {amos.pipeline._cascading_extractor is not None}")
    if amos.pipeline._cascading_extractor:
        print(f"   - use_llm: {amos.pipeline._cascading_extractor.use_llm}")
    
    # Test memory
    test_content = "Alice is a backend engineer who loves Python and works on microservices"
    
    print(f"\n2. Storing test memory...")
    print(f"   Content: {test_content}")
    
    memory = amos.remember(
        tenant_id="test-tenant",
        content=test_content,
        auto_process=False  # Don't process yet
    )
    
    print(f"   Memory ID: {memory.id}")
    
    # Process memory (this should trigger LLM)
    print(f"\n3. Processing memory with LLM extraction...")
    print("   (Watch for [LLM] debug output below)")
    print("-" * 60)
    
    report = amos.process_memory(
        tenant_id="test-tenant",
        memory_id=memory.id
    )
    
    print("-" * 60)
    print(f"\n4. Results:")
    print(f"   Facts extracted: {len(report.extracted_facts)}")
    
    if report.extracted_facts:
        print("\n   Extracted facts:")
        for fact in report.extracted_facts:
            print(f"   - {fact.entity} | {fact.attribute} | {fact.value}")
    else:
        print("\n   ⚠️  No facts extracted!")
        print("   This means LLM extraction is not working.")
    
    if report.extraction_sources:
        print(f"\n   Extraction sources:")
        for source, count in report.extraction_sources.items():
            print(f"   - {source}: {count} facts")
    
    print("\n" + "=" * 60)
    if report.extracted_facts:
        print("✓ LLM extraction is working!")
    else:
        print("✗ LLM extraction is NOT working")
        print("\nTroubleshooting:")
        print("1. Check if Ollama is running: curl http://localhost:11434/api/tags")
        print("2. Check if model is pulled: ollama list")
        print("3. Pull model if needed: ollama pull phi")
    print("=" * 60)

if __name__ == "__main__":
    main()

