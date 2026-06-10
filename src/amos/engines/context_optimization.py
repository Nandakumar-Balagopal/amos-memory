"""Context optimization through reference extraction and immediate memory.

Instead of compressing content, we:
1. Extract references (UUIDs, IDs, URLs) to immediate memory
2. Replace them with symbolic references in context
3. Agent can retrieve actual values on-demand via tool calls

This approach:
- Preserves semantic meaning (no comment removal)
- Reduces token usage (references → symbols)
- Enables on-demand retrieval (agent asks for specific IDs)
- Maintains code integrity (no compression artifacts)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass
class Reference:
    """A reference extracted from content."""
    type: str  # 'uuid', 'url', 'file_path', 'api_key', etc.
    value: str
    symbol: str  # Symbolic reference like @uuid_1, @url_2
    context: str  # Surrounding context for disambiguation


@dataclass
class ImmediateMemory:
    """Immediate memory store for references.
    
    This is like a scratchpad that the agent can query:
    - "What is @uuid_1?" → Returns actual UUID
    - "Show me @url_2" → Returns actual URL
    - "Get @file_3" → Returns file path
    """
    references: dict[str, Reference] = field(default_factory=dict)
    
    def add(self, ref: Reference) -> str:
        """Add reference and return its symbol."""
        self.references[ref.symbol] = ref
        return ref.symbol
    
    def get(self, symbol: str) -> Optional[Reference]:
        """Retrieve reference by symbol."""
        return self.references.get(symbol)
    
    def list_by_type(self, ref_type: str) -> list[Reference]:
        """List all references of a specific type."""
        return [ref for ref in self.references.values() if ref.type == ref_type]
    
    def clear(self):
        """Clear all references."""
        self.references.clear()


class ReferenceExtractor:
    """Extract references from content and replace with symbols."""
    
    # Patterns for different reference types
    UUID_PATTERN = re.compile(
        r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        re.IGNORECASE
    )
    
    URL_PATTERN = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE
    )
    
    FILE_PATH_PATTERN = re.compile(
        r'(?:/[a-zA-Z0-9_.-]+)+/?|(?:[a-zA-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*)',
    )
    
    API_KEY_PATTERN = re.compile(
        r'\b(?:sk-|pk_live_|pk_test_)[a-zA-Z0-9]{20,}\b'
    )
    
    def __init__(self):
        self.immediate_memory = ImmediateMemory()
        self._counters = {'uuid': 0, 'url': 0, 'file_path': 0, 'api_key': 0}
    
    def extract_uuids(self, text: str) -> tuple[str, list[Reference]]:
        """Extract UUIDs and replace with symbols.
        
        Example:
            Input: "User 550e8400-e29b-41d4-a716-446655440000 logged in"
            Output: "User @uuid_1 logged in"
            References: [Reference(type='uuid', value='550e8400...', symbol='@uuid_1')]
        """
        references = []
        
        def replace_uuid(match):
            uuid_value = match.group(0)
            self._counters['uuid'] += 1
            symbol = f"@uuid_{self._counters['uuid']}"
            
            # Get surrounding context (20 chars before and after)
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end]
            
            ref = Reference(
                type='uuid',
                value=uuid_value,
                symbol=symbol,
                context=context
            )
            references.append(ref)
            self.immediate_memory.add(ref)
            
            return symbol
        
        processed_text = self.UUID_PATTERN.sub(replace_uuid, text)
        return processed_text, references
    
    def extract_urls(self, text: str) -> tuple[str, list[Reference]]:
        """Extract URLs and replace with symbols."""
        references = []
        
        def replace_url(match):
            url_value = match.group(0)
            self._counters['url'] += 1
            symbol = f"@url_{self._counters['url']}"
            
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end]
            
            ref = Reference(
                type='url',
                value=url_value,
                symbol=symbol,
                context=context
            )
            references.append(ref)
            self.immediate_memory.add(ref)
            
            return symbol
        
        processed_text = self.URL_PATTERN.sub(replace_url, text)
        return processed_text, references
    
    def extract_file_paths(self, text: str) -> tuple[str, list[Reference]]:
        """Extract file paths and replace with symbols."""
        references = []
        
        def replace_path(match):
            path_value = match.group(0)
            # Only process if it looks like a real path (has at least 2 segments)
            if path_value.count('/') < 2 and path_value.count('\\') < 2:
                return path_value
            
            self._counters['file_path'] += 1
            symbol = f"@file_{self._counters['file_path']}"
            
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end]
            
            ref = Reference(
                type='file_path',
                value=path_value,
                symbol=symbol,
                context=context
            )
            references.append(ref)
            self.immediate_memory.add(ref)
            
            return symbol
        
        processed_text = self.FILE_PATH_PATTERN.sub(replace_path, text)
        return processed_text, references
    
    def extract_api_keys(self, text: str) -> tuple[str, list[Reference]]:
        """Extract API keys and replace with symbols (security)."""
        references = []
        
        def replace_key(match):
            key_value = match.group(0)
            self._counters['api_key'] += 1
            symbol = f"@key_{self._counters['api_key']}"
            
            ref = Reference(
                type='api_key',
                value=key_value,
                symbol=symbol,
                context="[REDACTED FOR SECURITY]"
            )
            references.append(ref)
            self.immediate_memory.add(ref)
            
            return symbol
        
        processed_text = self.API_KEY_PATTERN.sub(replace_key, text)
        return processed_text, references
    
    def extract_all(self, text: str) -> tuple[str, list[Reference]]:
        """Extract all reference types from text.
        
        Args:
            text: Input text with references
            
        Returns:
            Tuple of (processed_text, all_references)
        """
        all_references = []
        
        # Extract in order of specificity (most specific first)
        text, api_refs = self.extract_api_keys(text)
        all_references.extend(api_refs)
        
        text, uuid_refs = self.extract_uuids(text)
        all_references.extend(uuid_refs)
        
        text, url_refs = self.extract_urls(text)
        all_references.extend(url_refs)
        
        text, path_refs = self.extract_file_paths(text)
        all_references.extend(path_refs)
        
        return text, all_references
    
    def get_reference(self, symbol: str) -> Optional[Reference]:
        """Retrieve reference by symbol (for agent tool calls)."""
        return self.immediate_memory.get(symbol)
    
    def list_references(self, ref_type: Optional[str] = None) -> list[Reference]:
        """List all references, optionally filtered by type."""
        if ref_type:
            return self.immediate_memory.list_by_type(ref_type)
        return list(self.immediate_memory.references.values())


@dataclass
class OptimizedContext:
    """Context optimized for token efficiency."""
    original_text: str
    optimized_text: str
    references: list[Reference]
    original_tokens: int
    optimized_tokens: int
    token_savings: int
    
    @property
    def savings_percent(self) -> float:
        """Calculate percentage of tokens saved."""
        if self.original_tokens == 0:
            return 0.0
        return (self.token_savings / self.original_tokens) * 100


class ContextOptimizer:
    """Optimize context by extracting references to immediate memory."""
    
    def __init__(self):
        self.extractor = ReferenceExtractor()
    
    def optimize(self, text: str) -> OptimizedContext:
        """Optimize text by extracting references.
        
        Args:
            text: Input text
            
        Returns:
            OptimizedContext with references extracted
        """
        # Estimate original tokens (rough: 1 token ≈ 4 chars)
        original_tokens = len(text) // 4
        
        # Extract references
        optimized_text, references = self.extractor.extract_all(text)
        
        # Estimate optimized tokens
        optimized_tokens = len(optimized_text) // 4
        
        return OptimizedContext(
            original_text=text,
            optimized_text=optimized_text,
            references=references,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            token_savings=original_tokens - optimized_tokens
        )
    
    def optimize_batch(self, texts: list[str]) -> list[OptimizedContext]:
        """Optimize multiple texts."""
        return [self.optimize(text) for text in texts]
    
    def get_reference(self, symbol: str) -> Optional[Reference]:
        """Get reference by symbol (for agent tool calls)."""
        return self.extractor.get_reference(symbol)
    
    def list_references(self, ref_type: Optional[str] = None) -> list[Reference]:
        """List all references in immediate memory."""
        return self.extractor.list_references(ref_type)


# Agent tool interface
def create_reference_tools():
    """Create tool definitions for agent to query immediate memory.
    
    Returns:
        List of tool definitions for agent
    """
    return [
        {
            "name": "get_reference",
            "description": "Retrieve the actual value of a reference symbol like @uuid_1, @url_2, @file_3",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The reference symbol (e.g., @uuid_1)"
                    }
                },
                "required": ["symbol"]
            }
        },
        {
            "name": "list_references",
            "description": "List all available references of a specific type",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["uuid", "url", "file_path", "api_key"],
                        "description": "Type of references to list"
                    }
                }
            }
        }
    ]


# Made with Bob