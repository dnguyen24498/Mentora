"""The domain/adapter boundary is real and enforced (V0-012).

Acceptance criterion: *"Provider SDK does not leak into classroom domain."* An
assertion in prose is worth little, so this test reads the actual import graph of
``app/speech`` and proves the domain depends on nothing but itself and the stdlib:
a vendor SDK, a framework, or even another ``app`` package cannot appear there. The
adapter is allowed to depend on the port; the port is never allowed to depend on
the adapter.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SPEECH_DIR = BACKEND / "app" / "speech"
PROVIDERS_DIR = BACKEND / "app" / "providers"


def _absolute_imports(path: Path) -> list[str]:
    """Every absolute module name imported by ``path`` (relative imports excluded)."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_the_domain_imports_nothing_but_itself_and_the_stdlib():
    modules = sorted(SPEECH_DIR.glob("*.py"))
    assert modules, "expected the speech domain to exist"

    for path in modules:
        for name in _absolute_imports(path):
            if name == "app" or name.startswith("app."):
                assert name == "app.speech" or name.startswith("app.speech."), (
                    f"{path.name} imports {name!r}; the speech domain must not depend "
                    "on an adapter, the classroom domain, or any other app package"
                )
            else:
                root = name.split(".")[0]
                assert root not in {"fastapi", "pydantic", "starlette"}, (
                    f"{path.name} imports the web framework {name!r}; the domain is "
                    "framework-independent"
                )


def test_the_adapter_depends_on_the_port_not_the_reverse():
    adapter = PROVIDERS_DIR / "deterministic.py"
    imported = _absolute_imports(adapter)

    assert any(
        name == "app.speech" or name.startswith("app.speech.") for name in imported
    ), "the adapter must implement the domain port"
    # And the reverse edge must not exist anywhere in the domain.
    assert not any(
        name == "app.providers" or name.startswith("app.providers.")
        for path in SPEECH_DIR.glob("*.py")
        for name in _absolute_imports(path)
    )
