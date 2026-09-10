"""Async Search & Caching - Parallel API Calls & Result Caching

Uses asyncio to parallelize web searches, embedding generation, and API calls.
Implements smart caching to reduce redundant requests and API costs.
"""

import asyncio
import hashlib
from typing import List, Dict, Any, Optional, Callable, Coroutine
from functools import wraps
import json
from datetime import datetime, timedelta
import streamlit as st
from pathlib import Path


class AsyncCache:
    """Simple file-based async cache for API responses."""
    
    def __init__(self, cache_dir: str = "./async_cache", ttl_hours: int = 24):
        """Initialize cache.
        
        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Time-to-live in hours
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
    
    def _make_key(self, namespace: str, query: str) -> str:
        """Generate cache key from query.
        
        Args:
            namespace: Cache namespace (e.g., 'web_search', 'embedding')
            query: Query string
        
        Returns:
            Cache key (hashed)
        """
        content = f"{namespace}:{query}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, namespace: str, query: str) -> Optional[Any]:
        """Get cached value.
        
        Args:
            namespace: Cache namespace
            query: Query string
        
        Returns:
            Cached value or None if expired/missing
        """
        key = self._make_key(namespace, query)
        cache_file = self.cache_dir / f"{key}.json"
        
        if not cache_file.exists():
            return None
        
        with open(cache_file, 'r') as f:
            data = json.load(f)
        
        # Check TTL
        created_at = datetime.fromisoformat(data["created_at"])
        if datetime.now() - created_at > self.ttl:
            cache_file.unlink()  # Delete expired entry
            return None
        
        return data["value"]
    
    def set(self, namespace: str, query: str, value: Any):
        """Store value in cache.
        
        Args:
            namespace: Cache namespace
            query: Query string
            value: Value to cache
        """
        key = self._make_key(namespace, query)
        cache_file = self.cache_dir / f"{key}.json"
        
        data = {
            "created_at": datetime.now().isoformat(),
            "query": query,
            "value": value
        }
        
        with open(cache_file, 'w') as f:
            json.dump(data, f)


class AsyncSearchEngine:
    """Async wrapper for parallel search operations."""
    
    def __init__(self, web_search_func: Callable, cache: AsyncCache = None):
        """Initialize search engine.
        
        Args:
            web_search_func: Function that takes query and returns search results
            cache: Optional AsyncCache instance
        """
        self.web_search_func = web_search_func
        self.cache = cache or AsyncCache()
    
    async def _search_single(self, query: str) -> Dict[str, Any]:
        """Perform a single search (can be cached).
        
        Args:
            query: Search query
        
        Returns:
            Search results
        """
        # Check cache first
        cached = self.cache.get("web_search", query)
        if cached is not None:
            return {"query": query, "results": cached, "cached": True}
        
        # Run search in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self.web_search_func, query)
        
        # Cache results
        self.cache.set("web_search", query, results)
        
        return {"query": query, "results": results, "cached": False}
    
    async def search_parallel(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Perform multiple searches in parallel.
        
        Args:
            queries: List of search queries
        
        Returns:
            List of search results
        """
        tasks = [self._search_single(q) for q in queries]
        return await asyncio.gather(*tasks)
    
    def search_many(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Synchronous wrapper for parallel searches.
        
        Args:
            queries: List of search queries
        
        Returns:
            List of search results
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.search_parallel(queries))


class AsyncEmbedder:
    """Async wrapper for parallel embedding generation."""
    
    def __init__(self, embedding_func: Callable, cache: AsyncCache = None):
        """Initialize embedder.
        
        Args:
            embedding_func: Function that takes text and returns embedding
            cache: Optional AsyncCache instance
        """
        self.embedding_func = embedding_func
        self.cache = cache or AsyncCache()
    
    async def _embed_single(self, text: str) -> Dict[str, Any]:
        """Generate embedding for single text.
        
        Args:
            text: Text to embed
        
        Returns:
            Embedding result
        """
        # Check cache
        cached = self.cache.get("embedding", text)
        if cached is not None:
            return {"text": text[:50], "embedding": cached, "cached": True}
        
        # Generate in thread pool
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(None, self.embedding_func, text)
        
        # Cache
        self.cache.set("embedding", text, embedding)
        
        return {"text": text[:50], "embedding": embedding, "cached": False}
    
    async def embed_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Generate embeddings in parallel.
        
        Args:
            texts: List of texts to embed
        
        Returns:
            List of embedding results
        """
        tasks = [self._embed_single(t) for t in texts]
        return await asyncio.gather(*tasks)
    
    def embed_many(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Synchronous wrapper for parallel embeddings.
        
        Args:
            texts: List of texts
        
        Returns:
            List of results
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.embed_batch(texts))


def render_async_progress():
    """Render real-time progress indicator for async operations."""
    if "async_operations" not in st.session_state:
        st.session_state.async_operations = []
    
    if st.session_state.async_operations:
        with st.spinner("🔄 Processing queries in parallel..."):
            st.progress(0.5)  # Placeholder
