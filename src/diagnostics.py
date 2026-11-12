"""Human-friendly error reporting: file:line:col + source snippet + caret.

Phase errors are raised as `"line:col: message"` (several may be joined by
newlines). This module turns those strings into compiler-style diagnostics:

    examples/error.mb:2:1: error: cannot assign 'str' to 'int' in 'let x'
       2 | let x: int = "oops";
         | ^
"""
import re

_DIAG = re.compile(r"^(\d+):(\d+): (.*)$")


def _snippet(lines: list[str], line: int, col: int, context: int = 0) -> list[str]:
    if not (1 <= line <= len(lines)):
        return []
    start = max(1, line - context)
    end = min(len(lines), line + context)
    out = []
    width = max(4, len(str(end)))
    for n in range(start, end + 1):
        text = lines[n - 1].expandtabs(4)
        marker = ">" if n == line else " "
        out.append(f"{n:>{width}} {marker} {text}")
        if n == line:
            prefix = lines[line - 1][: max(0, col - 1)]
            pad = len(prefix.expandtabs(4))
            out.append(f"{'':>{width}}   {' ' * pad}^")
    return out


def format_diagnostics(path: str, source: str, messages: str) -> str:
    """Format one or more `line:col: message` errors with source context."""
    lines = source.splitlines()
    out: list[str] = []
    for raw in messages.splitlines():
        m = _DIAG.match(raw)
        if not m:
            out.append(f"{path}: error: {raw}")
            continue
        line, col, msg = int(m.group(1)), int(m.group(2)), m.group(3)
        out.append(f"{path}:{line}:{col}: error: {msg}")
        out.extend(_snippet(lines, line, col))
    return "\n".join(out)


def format_runtime_error(path: str, messages: str) -> str:
    out = []
    for raw in messages.splitlines():
        msg = raw[len("runtime: "):] if raw.startswith("runtime: ") else raw
        out.append(f"{path}: runtime error: {msg}")
    return "\n".join(out)
