from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .config import settings

try:
    from braintrust import trace
except Exception:  # pragma: no cover
    trace = None  # type: ignore


@contextmanager
def maybe_trace(name: str) -> Iterator[None]:
    if settings.AGENT_ENABLE_BRAINTRUST and trace is not None:
        with trace(name):
            yield
    else:
        yield


__all__ = ["maybe_trace"]
