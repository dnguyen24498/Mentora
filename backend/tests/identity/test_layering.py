"""The identity domain must not depend on an adapter, a framework or another domain.

``AI_IMPLEMENTATION_GUIDE.md``: *"invent a provider-specific contract in domain
code"* is forbidden, and ``PROMPT.md`` requires domain logic to stay independent of
provider SDKs. The same rule V0-012 enforces for the speech domain
(``tests/speech/test_layering.py``) applies here: the credential capability lives in
``app.providers`` and depends on ``app.identity`` — never the other way round.

The API layer is excluded on purpose: the transport may import the domain (it does,
to build principals), but the domain may not import the transport.
"""

from __future__ import annotations

import ast
from pathlib import Path

IDENTITY_DIR = Path(__file__).resolve().parents[2] / "app" / "identity"

#: Modules the domain may never reach for, and why.
FORBIDDEN_PREFIXES = {
    "app.providers": "an adapter must depend on the domain, not the reverse",
    "app.api": "the domain must not know the transport",
    "app.classroom": "domain modules stay independent of each other",
    "app.publication": "domain modules stay independent of each other",
    "app.compiler": "domain modules stay independent of each other",
    "fastapi": "no HTTP framework in the domain",
    "starlette": "no HTTP framework in the domain",
    "pydantic": "no transport validation in the domain",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_identity_domain_does_not_import_an_adapter_or_a_framework():
    offenders: list[str] = []

    for path in sorted(IDENTITY_DIR.glob("*.py")):
        for module in _imported_modules(path):
            for prefix, reason in FORBIDDEN_PREFIXES.items():
                if module == prefix or module.startswith(prefix + "."):
                    offenders.append(f"{path.name} imports {module}: {reason}")

    assert offenders == []


def test_identity_modules_are_scanned():
    """A guard against the check silently covering nothing."""

    assert len(list(IDENTITY_DIR.glob("*.py"))) >= 8
