"""Minimal, dependency-free S-expression reader/writer for KiCad file formats.

KiCad's ``.kicad_sym``, ``.kicad_mod``, ``.kicad_sch``, ``.kicad_pcb`` and netlist
files are S-expressions. This module parses them into nested Python lists whose
atoms are :class:`Sym` (bare symbols) or ``str`` (quoted strings), and can write
them back. Numbers stay as :class:`Sym` so that round-tripping is lossless;
helpers convert on access.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Union


class Sym(str):
    """A bare (unquoted) S-expression atom such as ``symbol`` or ``1.27``."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Sym({str.__repr__(self)})"


Node = Union[list, Sym, str]


class SExprError(ValueError):
    pass


def parse(text: str) -> list:
    """Parse a single top-level S-expression."""
    pos = 0
    n = len(text)
    stack: list[list] = []
    result: list | None = None

    while pos < n:
        c = text[pos]
        if c in " \t\r\n":
            pos += 1
        elif c == "(":
            new: list = []
            if stack:
                stack[-1].append(new)
            stack.append(new)
            pos += 1
        elif c == ")":
            if not stack:
                raise SExprError(f"unbalanced ')' at offset {pos}")
            done = stack.pop()
            if not stack:
                result = done
                pos += 1
                break
            pos += 1
        elif c == '"':
            pos += 1
            buf = []
            while True:
                if pos >= n:
                    raise SExprError("unterminated string")
                ch = text[pos]
                if ch == "\\" and pos + 1 < n:
                    nxt = text[pos + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                    pos += 2
                    continue
                if ch == '"':
                    pos += 1
                    break
                buf.append(ch)
                pos += 1
            if not stack:
                raise SExprError("string outside of list")
            stack[-1].append("".join(buf))
        else:
            start = pos
            while pos < n and text[pos] not in ' \t\r\n()"':
                pos += 1
            if not stack:
                raise SExprError("atom outside of list")
            stack[-1].append(Sym(text[start:pos]))

    if result is None:
        raise SExprError("no complete expression found")
    return result


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def dumps(node: Node, indent: int = 0) -> str:
    """Serialise a node. Lists containing lists are broken over lines."""
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        return _quote(node)
    if isinstance(node, (int, float)):
        return fmt_num(node)
    if not isinstance(node, list):
        raise TypeError(f"cannot serialise {type(node)!r}")
    has_children = any(isinstance(x, list) for x in node)
    if not has_children:
        return "(" + " ".join(dumps(x) for x in node) + ")"
    pad = "  " * (indent + 1)
    parts: list[str] = []
    head: list[str] = []
    for x in node:
        if isinstance(x, list):
            break
        head.append(dumps(x))
    rest = node[len(head):]
    out = "(" + " ".join(head)
    for x in rest:
        parts.append("\n" + pad + dumps(x, indent + 1))
    return out + "".join(parts) + "\n" + "  " * indent + ")"


def fmt_num(v: float | int) -> str:
    if isinstance(v, int):
        return str(v)
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def tag(node: Node) -> str | None:
    if isinstance(node, list) and node and isinstance(node[0], Sym):
        return str(node[0])
    return None


def children(node: list, name: str) -> Iterator[list]:
    for x in node[1:]:
        if isinstance(x, list) and tag(x) == name:
            yield x


def child(node: list, name: str) -> list | None:
    return next(children(node, name), None)


def value(node: list | None, index: int = 1, default=None):
    if node is None or len(node) <= index:
        return default
    return node[index]


def num(node: list | None, index: int = 1, default: float = 0.0) -> float:
    v = value(node, index)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def has_flag(node: list, flag: str) -> bool:
    """True if ``flag`` appears as a bare atom or as ``(flag yes)`` (KiCad 8+)."""
    for x in node[1:]:
        if isinstance(x, Sym) and x == flag:
            return True
        if isinstance(x, list) and tag(x) == flag:
            return value(x) in (None, "yes", Sym("yes"))
    return False


def is_hidden(node: list) -> bool:
    """Visibility for properties/pins: KiCad 7 uses ``hide`` inside ``effects``;
    KiCad 8+ uses ``(hide yes)`` either at node or effects level."""
    if has_flag(node, "hide"):
        return True
    eff = child(node, "effects")
    return bool(eff is not None and has_flag(eff, "hide"))
