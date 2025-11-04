from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .config import settings

try:
    from braintrust import init_logger, wrap_openai, start_span
    BRAINTRUST_AVAILABLE = True
except Exception:  # pragma: no cover
    start_span = None  # type: ignore
    init_logger = None  # type: ignore
    wrap_openai = None  # type: ignore
    BRAINTRUST_AVAILABLE = False

_logger_initialized = False
_log_dir: Optional[Path] = None
_log_dir_created_for_run: bool = False


def reset_log_directory() -> None:
    """
    Reset the log directory cache to allow a new directory to be created for the next run.
    This should be called at the start of each new processing run.
    """
    global _log_dir, _log_dir_created_for_run
    _log_dir = None
    _log_dir_created_for_run = False


def get_log_directory(force_new: bool = False) -> Optional[Path]:
    """
    Get or create the timestamped log directory for local logging.
    
    Each call with force_new=True or on first call will create a new directory.
    Subsequent calls without force_new will return the same directory.
    
    Args:
        force_new: If True, creates a new directory even if one already exists
        
    Returns:
        Path to the log directory, or None if local logging is disabled
    """
    global _log_dir, _log_dir_created_for_run
    
    # Only create log directory when local logging is enabled
    if not settings.AGENT_ENABLE_LOCAL_LOGS:
        return None
    
    # If force_new is True or this is the first call, create a new directory
    if force_new or _log_dir is None:
        # Create logs directory with timestamp
        # src/telemetry.py -> src -> project root
        project_root = Path(__file__).resolve().parent.parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log_dir = project_root / "logs" / f"log_{timestamp}"
        _log_dir.mkdir(parents=True, exist_ok=True)
        _log_dir_created_for_run = True
    
    return _log_dir


def init_braintrust_logger() -> bool:
    """
    Initialize Braintrust logger if enabled and available.
    
    Returns:
        True if logger was initialized, False otherwise
    """
    global _logger_initialized
    
    if _logger_initialized:
        return True
    
    if not settings.AGENT_ENABLE_BRAINTRUST or not BRAINTRUST_AVAILABLE:
        return False
    
    if not settings.BRAINTRUST_API_KEY:
        return False
    
    try:
        if init_logger is not None:
            # Get or create log directory for local logging (don't force new here since
            # it may be called multiple times during initialization)
            log_dir = get_log_directory(force_new=False)
            
            # Initialize the Braintrust logger (this sets it as the default logger)
            logger = init_logger(
                project="note-agent",  # Project name
                api_key=settings.BRAINTRUST_API_KEY,
            )
            
            # If local logging is enabled, write metadata to log directory
            if log_dir is not None:
                metadata_file = log_dir / "metadata.json"
                import json
                metadata = {
                    "project": "note-agent",
                    "timestamp": datetime.now().isoformat(),
                    "braintrust_enabled": True,
                    "log_directory": str(log_dir),
                }
                metadata_file.write_text(json.dumps(metadata, indent=2))
                
                # Write a note that Braintrust logs will be visible in the Braintrust dashboard
                # and that local logs can be extracted via Braintrust API if needed
                readme_file = log_dir / "README.txt"
                readme_file.write_text(
                    "Braintrust Log Directory\n"
                    "=======================\n\n"
                    f"Created: {datetime.now().isoformat()}\n"
                    "Project: note-agent\n\n"
                    "Braintrust logs are sent to the Braintrust cloud service.\n"
                    "This directory is created for local tracking and metadata.\n"
                    "To view full logs, visit your Braintrust dashboard.\n"
                )
            
            _logger_initialized = True
            return True
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize Braintrust logger: {e}")
    
    return False


def wrap_openai_client(client):
    """
    Wrap an OpenAI client with Braintrust tracing if enabled.
    
    Per Braintrust docs: wrap_openai automatically uses the initialized logger
    from init_logger. See: https://www.braintrust.dev/docs/providers/openai#trace-automatically-with-wrapopenai
    
    Args:
        client: OpenAI client instance
        
    Returns:
        Wrapped client if Braintrust is enabled, original client otherwise
    """
    if not settings.AGENT_ENABLE_BRAINTRUST or not BRAINTRUST_AVAILABLE:
        return client
    
    if wrap_openai is None:
        return client
    
    try:
        # Initialize logger if not already initialized
        if init_braintrust_logger():
            # wrap_openai automatically uses the initialized logger from initLogger
            return wrap_openai(client)
    except Exception:
        pass
    
    return client


@contextmanager
def maybe_trace(name: str) -> Iterator[None]:
    if settings.AGENT_ENABLE_BRAINTRUST and start_span is not None:
        with start_span(name=name):
            yield
    else:
        yield


__all__ = ["maybe_trace", "init_braintrust_logger", "wrap_openai_client", "get_log_directory", "reset_log_directory"]
