import json
import logging
import sys
import textwrap
from pathlib import Path
from typing import Optional

from .config import settings


def _filter_base64_images(text: str) -> str:
    """
    Remove base64 image data from log messages to reduce log size.
    
    Replaces patterns like:
    - data:image/jpeg;base64,/9j/4AAQ... (very long base64 string)
    - "image_url": {"url": "data:image/jpeg;base64,..."}
    
    With placeholders indicating the data was present.
    """
    import re
    
    # Pattern to match data:image URLs with base64 data
    # Matches: data:image/[type];base64,<base64_data>
    pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}'
    
    def replace_base64(match):
        # Extract image type from the match
        match_str = match.group(0)
        # Get the type (jpeg, png, etc.)
        type_match = re.search(r'data:image/([^;]+)', match_str)
        img_type = type_match.group(1) if type_match else "image"
        # Return placeholder with approximate size
        size = len(match_str)
        return f'data:image/{img_type};base64,[...{size} chars of base64 data excluded...]'
    
    text = re.sub(pattern, replace_base64, text)
    
    # Also handle base64 data in JSON structures more specifically
    # Pattern for base64 data in "data" fields (Anthropic format)
    json_base64_pattern = r'"data"\s*:\s*"[A-Za-z0-9+/=]{100,}"'
    text = re.sub(json_base64_pattern, '"data": "[...base64 image data excluded...]"', text)
    
    return text


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\x1b[36m",  # cyan
        logging.INFO: "\x1b[32m",   # green
        logging.WARNING: "\x1b[33m",# yellow
        logging.ERROR: "\x1b[31m",  # red
        logging.CRITICAL: "\x1b[35m", # magenta
    }
    RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        msg = record.getMessage()
        # Filter base64 images from console output too (though they're less likely there)
        msg = _filter_base64_images(msg)
        
        # Temporarily replace message for formatting
        original_msg = record.msg
        record.msg = msg
        message = super().format(record)
        record.msg = original_msg  # Restore original
        
        if color:
            return f"{color}{message}{self.RESET}"
        return message


def _pretty_format_json(data: str) -> str:
    """
    Try to pretty-format JSON strings, fallback to original if not valid JSON.
    """
    try:
        # Try to parse as JSON
        parsed = json.loads(data)
        # Pretty print with indentation
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        # Not JSON, return as-is
        return data


def _format_long_content(content: str, max_line_length: int = 120, indent: str = "  ") -> str:
    """
    Wrap long content lines with proper indentation for continuation lines.
    """
    lines = content.split('\n')
    wrapped_lines = []
    
    for line in lines:
        if len(line) <= max_line_length:
            wrapped_lines.append(line)
        else:
            # Try to wrap at word boundaries
            wrapped = textwrap.fill(
                line,
                width=max_line_length,
                initial_indent="",
                subsequent_indent=indent,
                break_long_words=True,
                break_on_hyphens=False
            )
            wrapped_lines.append(wrapped)
    
    return '\n'.join(wrapped_lines)


class _DetailedFormatter(logging.Formatter):
    """Detailed formatter for file logs with optimization data and human-readable formatting."""
    
    MAX_LINE_LENGTH = 120
    INDENT_CONTINUATION = "  │ "
    
    # Track last module/function for section detection
    _last_module_func = None
    
    def _add_section_separator_if_needed(self, record: logging.LogRecord) -> str:
        """
        Add visual separator if we're transitioning to a different major section.
        """
        current = f"{record.name}.{record.funcName}"
        separator = ""
        
        # Check if we've changed to a different major module/section
        if self._last_module_func and self._last_module_func != current:
            # Only add separator for significant transitions
            last_module = self._last_module_func.split('.')[0] if '.' in self._last_module_func else self._last_module_func
            current_module = current.split('.')[0] if '.' in current else current
            
            # Add separator when switching between major modules (e.g., pipeline -> llm -> context)
            if last_module != current_module:
                separator = f"\n{'─' * 120}\n"
        
        self._last_module_func = current
        return separator
    
    def format(self, record: logging.LogRecord) -> str:
        # Get the message first
        msg = record.getMessage()
        
        # Filter out base64 image data
        msg = _filter_base64_images(msg)
        
        # Build header part (timestamp, level, location)
        header_fmt = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)s:%(lineno)d"
        header = header_fmt % {
            'asctime': self.formatTime(record, self.datefmt),
            'levelname': record.levelname,
            'name': record.name,
            'funcName': record.funcName,
            'lineno': record.lineno,
        }
        
        # Check if message contains JSON-like structures that should be formatted
        # Look for patterns like {'key': 'value'} or {"key": "value"}
        formatted_msg = msg
        
        # Try to detect and format JSON in the message
        # Look for common JSON patterns (dict literals, JSON strings)
        if '{' in msg and ('}' in msg or '"' in msg or "'" in msg):
            # Try to extract and format JSON-like content
            # This is a simple heuristic - may not catch all cases
            try:
                # Look for JSON structure in message
                if ('json_data' in msg or 'args=' in msg or 'kwargs=' in msg or 
                    'Request options' in msg or 'return_value=' in msg):
                    # Try to extract JSON-like structures
                    # For now, we'll handle this in the full formatting below
                    pass
            except Exception:
                pass
        
        # Format extra fields
        extra_parts = []
        if hasattr(record, 'duration'):
            extra_parts.append(f"duration={record.duration:.3f}s")
        
        # Format args and kwargs more intelligently
        if hasattr(record, 'args') and record.args != ():
            args_str = str(record.args)
            args_str = _filter_base64_images(args_str)
            # Try to pretty-print if it looks like JSON
            if '{' in args_str or '[' in args_str:
                args_str = _pretty_format_json(args_str) if ('{' in args_str and args_str.count('{') == 1) else args_str
            extra_parts.append(f"args={args_str}")
        
        if hasattr(record, 'kwargs') and record.kwargs:
            kwargs_str = str(record.kwargs)
            kwargs_str = _filter_base64_images(kwargs_str)
            # Try to pretty-print if it looks like JSON
            if '{' in kwargs_str or '[' in kwargs_str:
                kwargs_str = _pretty_format_json(kwargs_str) if ('{' in kwargs_str and kwargs_str.count('{') == 1) else kwargs_str
            extra_parts.append(f"kwargs={kwargs_str}")
        
        # Build the full message
        full_message = formatted_msg
        if extra_parts:
            full_message += " | " + " | ".join(extra_parts)
        
        # Wrap long lines (handles JSON-like structures naturally through wrapping)
        wrapped_message = _format_long_content(full_message, self.MAX_LINE_LENGTH, self.INDENT_CONTINUATION)
        
        # Add section separator if needed
        separator = self._add_section_separator_if_needed(record)
        
        # Combine header with message
        result = f"{separator}{header}\n{self.INDENT_CONTINUATION}{wrapped_message.replace(chr(10), chr(10) + self.INDENT_CONTINUATION)}"
        
        # Add exception info if present (also filter base64 from exception tracebacks)
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            exc_text = _filter_base64_images(exc_text)
            # Indent exception traceback
            exc_lines = exc_text.split('\n')
            indented_exc = '\n'.join(self.INDENT_CONTINUATION + line for line in exc_lines)
            result += f"\n{indented_exc}"
        
        return result


def setup_logging(level: Optional[str] = None, log_dir: Optional[Path] = None) -> None:
    """
    Set up logging with both console and file handlers.
    
    Args:
        level: Optional log level override
        log_dir: Optional directory to write log files (if None, tries to get from telemetry)
    """
    log_level = (level or settings.LOG_LEVEL).upper()
    root = logging.getLogger()
    root.setLevel(log_level)

    # Clear previous handlers in case of re-init
    root.handlers.clear()

    # Console handler with colors (for development)
    console_handler = logging.StreamHandler(sys.stdout)
    console_fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    console_handler.setFormatter(_ColorFormatter(console_fmt))
    root.addHandler(console_handler)

    # File handler for detailed logs (if log directory is available)
    if log_dir is None:
        # Try to get log directory from telemetry module
        try:
            from .telemetry import get_log_directory
            log_dir = get_log_directory()
        except Exception:
            log_dir = None
    
    if log_dir is not None:
        log_file = log_dir / "detailed.log"
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Always DEBUG for file logs
        file_handler.setFormatter(_DetailedFormatter())
        root.addHandler(file_handler)
        
        # Also log httpx requests if DEBUG is enabled
        if log_level == "DEBUG":
            # Enable debug logging for httpx and other HTTP libraries
            logging.getLogger("httpx").setLevel(logging.DEBUG)
            logging.getLogger("httpcore").setLevel(logging.DEBUG)
            logging.getLogger("urllib3").setLevel(logging.DEBUG)


__all__ = ["setup_logging"]
