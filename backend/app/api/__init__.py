"""The HTTP transport package.

``create_app`` is resolved **lazily** (PEP 562). Importing it eagerly would put the
whole application factory — and its imports back into the domain routers — into the
import graph of every request, so ``app.classroom.router`` importing
``app.api.security`` would then be a circular import. Resolving it on first attribute
access keeps ``from app.api import create_app`` working without that cycle.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from app.api.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["create_app"]
