import logging
import sys
from typing import Optional

from .config import settings


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
        message = super().format(record)
        if color:
            return f"{color}{message}{self.RESET}"
        return message


def setup_logging(level: Optional[str] = None) -> None:
    log_level = (level or settings.LOG_LEVEL).upper()
    root = logging.getLogger()
    root.setLevel(log_level)

    # Clear previous handlers in case of re-init in notebooks
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    handler.setFormatter(_ColorFormatter(fmt))
    root.addHandler(handler)


__all__ = ["setup_logging"]
