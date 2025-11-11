"""In-memory LRU cache for job results."""

import time
from collections import OrderedDict
from typing import Any, Dict, Optional
from threading import Lock


class LRUCache:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of entries to cache
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if exists and not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # Check if expired
            if time.time() - entry["timestamp"] > self.ttl_seconds:
                del self._cache[key]
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return entry["value"]
    
    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            # If key exists, remove it first
            if key in self._cache:
                del self._cache[key]
            
            # Add new entry
            self._cache[key] = {
                "value": value,
                "timestamp": time.time()
            }
            
            # Evict oldest if over size
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
    
    def delete(self, key: str) -> bool:
        """
        Delete entry from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def list_keys(self) -> list[str]:
        """
        List all non-expired keys in cache.
        
        Returns:
            List of cache keys
        """
        with self._lock:
            current_time = time.time()
            valid_keys = []
            expired_keys = []
            
            for key, entry in self._cache.items():
                if current_time - entry["timestamp"] > self.ttl_seconds:
                    expired_keys.append(key)
                else:
                    valid_keys.append(key)
            
            # Clean up expired keys
            for key in expired_keys:
                del self._cache[key]
            
            return valid_keys
    
    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)

