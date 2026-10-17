"""Font-free text metrics for the platform flow layout (V0-019).

The ``themed`` mode re-lays out the extracted content into the platform's own
grid, so it must answer two questions without a font: *how wide is this string*
and *where does this line break*. Bundling a font and a shaper would add a
dependency and a licence, and the renderer technology is still an OPEN decision
(``DEC-TECH-005``), so the metrics are a **table of per-character advances** in
1/1000 em for a Helvetica/Arial-metric sans — the family the theme's stack
resolves to on a host without the preferred one.

Two properties matter:

* **It is deterministic.** The same string measures the same on every machine,
  which is what makes a rendered slide reproducible.
* **It cannot cause a collision.** The flow places blocks on a cursor, so a
  wrapping error is confined to its own block; the estimates are additionally
  biased *wide* (:data:`SAFETY`), so a line breaks a hair early rather than
  running past its column.

Non-ASCII text (this platform renders Vietnamese) is handled by decomposing a
character to its base letter — ``ấ`` measures as ``a`` — which is what the
metric table is for.
"""

from __future__ import annotations

import unicodedata

#: Helvetica/Arial advance widths in 1/1000 em. Anything not listed measures as
#: :data:`_DEFAULT`.
_ADVANCES: dict[str, int] = {
    " ": 278,
    "!": 278,
    '"': 355,
    "#": 556,
    "$": 556,
    "%": 889,
    "&": 667,
    "'": 191,
    "(": 333,
    ")": 333,
    "*": 389,
    "+": 584,
    ",": 278,
    "-": 333,
    ".": 278,
    "/": 278,
    ":": 278,
    ";": 278,
    "<": 584,
    "=": 584,
    ">": 584,
    "?": 556,
    "@": 1015,
    "[": 278,
    "\\": 278,
    "]": 278,
    "^": 469,
    "_": 556,
    "`": 333,
    "{": 334,
    "|": 260,
    "}": 334,
    "~": 584,
    "A": 667,
    "B": 667,
    "C": 722,
    "D": 722,
    "E": 667,
    "F": 611,
    "G": 778,
    "H": 722,
    "I": 278,
    "J": 500,
    "K": 667,
    "L": 556,
    "M": 833,
    "N": 722,
    "O": 778,
    "P": 667,
    "Q": 778,
    "R": 722,
    "S": 667,
    "T": 611,
    "U": 722,
    "V": 667,
    "W": 944,
    "X": 667,
    "Y": 667,
    "Z": 611,
    "a": 556,
    "b": 556,
    "c": 500,
    "d": 556,
    "e": 556,
    "f": 278,
    "g": 556,
    "h": 556,
    "i": 222,
    "j": 222,
    "k": 500,
    "l": 222,
    "m": 833,
    "n": 556,
    "o": 556,
    "p": 556,
    "q": 556,
    "r": 333,
    "s": 500,
    "t": 278,
    "u": 556,
    "v": 500,
    "w": 722,
    "x": 500,
    "y": 500,
    "z": 500,
    # Punctuation and symbols the extractor emits after PowerPoint substitution.
    "\u00a0": 278,  # no-break space
    "\u2013": 556,  # en dash
    "\u2014": 1000,  # em dash
    "\u2018": 222,
    "\u2019": 222,
    "\u201c": 333,
    "\u201d": 333,
    "\u2022": 350,  # bullet
    "\u2023": 350,
    "\u2026": 1000,  # ellipsis
    "\u0110": 722,  # Đ (no NFD decomposition)
    "\u0111": 556,  # đ
}
for _digit in "0123456789":
    _ADVANCES[_digit] = 556

_DEFAULT = 556

#: The theme's fonts are a little wider than the Helvetica table, so every
#: measurement is biased wide: a line breaks slightly early instead of running
#: past its column. Erring wide is invisible; erring narrow is not.
SAFETY = 1.05

#: Bold/italic widen a glyph run by a few percent.
_BOLD = 1.06
_ITALIC = 1.02


def advance(character: str) -> float:
    """Advance width of one character, in 1/1000 em."""

    width = _ADVANCES.get(character)
    if width is None:
        decomposed = unicodedata.normalize("NFD", character)
        width = _ADVANCES.get(decomposed[0], _DEFAULT) if decomposed else _DEFAULT
    return float(width)


def measure(text: str, size_px: float, *, bold: bool = False, italic: bool = False) -> float:
    """Width of ``text`` at ``size_px``, in px."""

    if not text:
        return 0.0
    em = sum(advance(character) for character in text) / 1000.0
    width = em * size_px * SAFETY
    if bold:
        width *= _BOLD
    if italic:
        width *= _ITALIC
    return width
