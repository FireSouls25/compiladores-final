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


def format_diagnostics(path: str, source: str, messages: str, kind: str | None = None) -> str:
    label = f"error {kind}" if kind else "error"
    lines = source.splitlines()
    out: list[str] = []
    for raw in messages.splitlines():
        m = _DIAG.match(raw)
        if not m:
            out.append(f"{path}: {label}: {raw}")
            continue
        line, col, msg = int(m.group(1)), int(m.group(2)), m.group(3)
        out.append(f"{path}:{line}:{col}: {label}: {msg}")
        out.extend(_snippet(lines, line, col))
    return "\n".join(out)


def format_runtime_error(path: str, messages: str) -> str:
    return "\n".join(f"{path}: error de ejecución: {raw}" for raw in messages.splitlines())
