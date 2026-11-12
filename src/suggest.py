"""Spelling suggestions for compiler diagnostics.

Uses optimal-string-alignment distance (Levenshtein + adjacent transposition),
which is what users expect for typos like `lenght` -> `length`.
"""


def distance(a: str, b: str) -> int:
    """Optimal string alignment distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
            if (
                i > 1
                and j > 1
                and ca == b[j - 2]
                and a[i - 2] == cb
            ):
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


def closest(name: str, candidates, max_distance: int | None = None) -> str | None:
    """Return the closest candidate, or None when nothing is close enough."""
    if len(name) < 3:
        return None
    if max_distance is None:
        max_distance = max(1, min(3, len(name) // 3))
    best = None
    best_d = None
    for candidate in sorted(set(candidates)):
        if candidate == name:
            continue
        d = distance(name.lower(), candidate.lower())
        if best_d is None or d < best_d or (d == best_d and candidate < best):
            best, best_d = candidate, d
    if best is None or best_d > max_distance:
        return None
    return best
