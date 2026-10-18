"""Static serving for the built frontend, with SPA history fallback.

The frontend has real client-side routes — ``/`` for the material library,
``/studio/{artifactId}`` for the Teacher Studio, ``/classroom/{classId}`` for the
classroom and ``/learn/{artifactId}`` for the learning page — so a deep link, a
bookmark or a page refresh must serve the app *shell* rather than a bare 404.

Plain ``StaticFiles(html=True)`` only answers ``index.html`` for *directory*
paths, so ``/studio/<uuid>`` would 404 in single-origin mode (the backend serving
``frontend/dist`` at ``/``). This subclass rewrites exactly that case:

* a real file is still served as itself (the hashed asset bundle included);
* a **missing file** still 404s, because rewriting ``/assets/index-abc.js`` to
  HTML would hand the browser a script it cannot parse;
* a non-GET/HEAD method keeps its 405.

A client route is recognised by the absence of a file extension in its last
segment, which is what distinguishes ``/studio/<uuid>`` (the app) from
``/assets/index-abc.js`` and ``/favicon.ico`` (files).
"""

from __future__ import annotations

import posixpath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope


def _looks_like_a_file(path: str) -> bool:
    """True when the last path segment has an extension (so a 404 is a real 404)."""

    return "." in posixpath.basename(path)


class SpaStaticFiles(StaticFiles):
    """``StaticFiles`` that falls back to ``index.html`` for an extension-less 404."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or _looks_like_a_file(path):
                raise
            # Client-side routing owns this path: hand back the app shell.
            # `no-cache` because the shell names the hashed asset bundle, so a
            # cached shell would pin an old deploy.
            response = await super().get_response("index.html", scope)
            response.headers["Cache-Control"] = "no-cache"
            return response


__all__ = ["SpaStaticFiles"]
