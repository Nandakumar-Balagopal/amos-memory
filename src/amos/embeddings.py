"""Embedding generation for semantic search."""

from __future__ import annotations

import numpy as np
from typing import Protocol


class EmbeddingModel(Protocol):
    """Protocol for embedding models."""
    
    def encode(self, text: str | list[str]) -> np.ndarray:
        """Generate embeddings for text."""
        ...
    
    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        ...


class SentenceTransformerEmbeddings:
    """Embeddings using sentence-transformers library."""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """Initialize with a sentence-transformers model.
        
        Default model: all-MiniLM-L6-v2 (OPTIMIZED FOR SPEED)
        - 22M parameters (6x smaller than nomic)
        - 384 dimensions (4x smaller vectors)
        - Very fast inference (~2ms on CPU vs 10ms)
        - Good quality for semantic search
        - Model size: 80MB vs 500MB
        
        Alternative models:
        - "BAAI/bge-small-en-v1.5" (384 dim, slightly better quality)
        - "thenlper/gte-small" (384 dim, balanced)
        - "nomic-ai/nomic-embed-text-v1.5" (768 dim, slower but better)
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "Install sentence-transformers: pip install sentence-transformers"
            ) from error
        
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        # Use native dimension (384 for all-MiniLM-L6-v2)
        try:
            self._native_dimension = self.model.get_embedding_dimension()
        except AttributeError:
            # Fallback for older versions
            self._native_dimension = self.model.get_sentence_embedding_dimension()
        self._dimension = self._native_dimension  # Use native dimension, no padding
    
    def encode(self, text: str | list[str]) -> np.ndarray:
        """Generate embeddings for text.
        
        Args:
            text: Single string or list of strings
            
        Returns:
            numpy array of shape (n, dimension) where n is number of texts
        """
        if isinstance(text, str):
            text = [text]
        
        # Generate embeddings (no padding/truncation needed)
        embeddings = self.model.encode(
            text,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        return embeddings
    
    @property
    def dimension(self) -> int:
        """Embedding dimension (384 for all-MiniLM-L6-v2)."""
        return self._dimension


class OpenAIEmbeddings:
    """Embeddings using OpenAI API (text-embedding-3-small)."""
    
    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small"):
        """Initialize with OpenAI API.
        
        Args:
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            model: Model name (text-embedding-3-small or text-embedding-3-large)
        """
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install openai: pip install openai") from error
        
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._dimension = 1536
    
    def encode(self, text: str | list[str]) -> np.ndarray:
        """Generate embeddings using OpenAI API.
        
        Args:
            text: Single string or list of strings
            
        Returns:
            numpy array of shape (n, 1536)
        """
        if isinstance(text, str):
            text = [text]
        
        response = self.client.embeddings.create(
            input=text,
            model=self.model,
            dimensions=self._dimension
        )
        
        embeddings = np.array([item.embedding for item in response.data])
        return embeddings
    
    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        return self._dimension


class CachedEmbeddings:
    """Wrapper that caches embeddings to avoid recomputation."""
    
    def __init__(self, model: EmbeddingModel, cache_size: int = 10000):
        """Initialize with an embedding model and cache size.
        
        Args:
            model: Underlying embedding model
            cache_size: Maximum number of cached embeddings
        """
        self.model = model
        self.cache: dict[str, np.ndarray] = {}
        self.cache_size = cache_size
        self.cache_order: list[str] = []
    
    def encode(self, text: str | list[str]) -> np.ndarray:
        """Generate embeddings with caching.
        
        Args:
            text: Single string or list of strings
            
        Returns:
            numpy array of embeddings
        """
        if isinstance(text, str):
            # Single text - check cache
            if text in self.cache:
                return self.cache[text].reshape(1, -1)
            
            # Generate and cache
            embedding = self.model.encode(text)
            self._add_to_cache(text, embedding[0])
            return embedding
        
        # Multiple texts - check cache for each
        cached_embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        for i, t in enumerate(text):
            if t in self.cache:
                cached_embeddings.append((i, self.cache[t]))
            else:
                uncached_texts.append(t)
                uncached_indices.append(i)
        
        # Generate embeddings for uncached texts
        if uncached_texts:
            new_embeddings = self.model.encode(uncached_texts)
            for t, emb in zip(uncached_texts, new_embeddings):
                self._add_to_cache(t, emb)
                cached_embeddings.append((uncached_indices[uncached_texts.index(t)], emb))
        
        # Sort by original index and return
        cached_embeddings.sort(key=lambda x: x[0])
        return np.array([emb for _, emb in cached_embeddings])
    
    def _add_to_cache(self, text: str, embedding: np.ndarray) -> None:
        """Add embedding to cache with LRU eviction."""
        if text in self.cache:
            # Move to end (most recently used)
            self.cache_order.remove(text)
            self.cache_order.append(text)
            return
        
        # Add new entry
        if len(self.cache) >= self.cache_size:
            # Evict least recently used
            oldest = self.cache_order.pop(0)
            del self.cache[oldest]
        
        self.cache[text] = embedding
        self.cache_order.append(text)
    
    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        return self.model.dimension


def get_default_embeddings() -> EmbeddingModel:
    """Get default embedding model (sentence-transformers).
    
    Returns:
        Cached sentence-transformers model
    """
    return CachedEmbeddings(
        SentenceTransformerEmbeddings(),
        cache_size=10000
    )

# Made with Bob
