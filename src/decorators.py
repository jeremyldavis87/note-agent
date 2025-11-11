"""
Decorators for caching and performance optimization.

This module provides decorators for caching expensive operations,
timing functions, and other performance optimizations.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Optional


logger = logging.getLogger(__name__)


def timed(func: Callable) -> Callable:
    """
    Decorator to log function execution time.
    
    Args:
        func: Function to time
        
    Returns:
        Wrapped function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        logger.debug(f"{func.__name__} completed in {duration:.3f}s")
        return result
    return wrapper


def cached_property(func: Callable) -> property:
    """
    Decorator to create a cached property (computed once, then cached).
    
    Similar to functools.cached_property but with better logging.
    
    Args:
        func: Property getter function
        
    Returns:
        Property object with caching
    """
    attr_name = f"_cached_{func.__name__}"
    
    @functools.wraps(func)
    def wrapper(self):
        if not hasattr(self, attr_name):
            logger.debug(f"Computing cached property: {func.__name__}")
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)
    
    return property(wrapper)


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator to retry a function on failure with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier for subsequent retries
        exceptions: Tuple of exceptions to catch and retry
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
            
            # Re-raise the last exception if all attempts failed
            raise last_exception
        
        return wrapper
    return decorator


def log_calls(func: Callable) -> Callable:
    """
    Decorator to log function calls with arguments.
    
    Useful for debugging and monitoring.
    
    Args:
        func: Function to log
        
    Returns:
        Wrapped function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"Calling {func.__name__}({signature})")
        
        result = func(*args, **kwargs)
        
        logger.debug(f"{func.__name__} returned {result!r}")
        return result
    
    return wrapper


def memoize(func: Callable) -> Callable:
    """
    Simple memoization decorator for functions with hashable arguments.
    
    For more complex caching needs, use functools.lru_cache.
    
    Args:
        func: Function to memoize
        
    Returns:
        Memoized function
    """
    cache = {}
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Create cache key from args and kwargs
        key = (args, tuple(sorted(kwargs.items())))
        
        if key not in cache:
            logger.debug(f"Cache miss for {func.__name__}{args}")
            cache[key] = func(*args, **kwargs)
        else:
            logger.debug(f"Cache hit for {func.__name__}{args}")
        
        return cache[key]
    
    # Add cache management methods
    wrapper.cache = cache
    wrapper.cache_clear = cache.clear
    
    return wrapper


__all__ = [
    "timed",
    "cached_property",
    "retry_on_failure",
    "log_calls",
    "memoize",
]

