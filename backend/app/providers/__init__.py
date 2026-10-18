"""Replaceable capability adapters (V0-012).

The adapters that sit behind a domain port live here, so the domain
(:mod:`app.speech`) never depends on one. V0-012 adds the neutral voice adapter;
the same directory is the home for the LLM/search/STT/SFU adapters later.

Nothing here implements a *vendor* technology: every provider choice is still
``OPEN`` in ``governance/DECISION_LEDGER.yaml``, so V0 ships deterministic local
implementations selected by a factory, exactly like the renderer and the index
builder.
"""

from __future__ import annotations

from app.providers.deterministic import DeterministicSpeechProvider
from app.providers.factory import (
    DEFAULT_SPEECH_PROVIDER,
    SPEECH_PROVIDERS,
    UnknownSpeechProviderError,
    build_speech_service,
    create_speech_provider,
)

__all__ = [
    "DEFAULT_SPEECH_PROVIDER",
    "SPEECH_PROVIDERS",
    "DeterministicSpeechProvider",
    "UnknownSpeechProviderError",
    "build_speech_service",
    "create_speech_provider",
]
