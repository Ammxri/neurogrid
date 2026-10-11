"""Platform-independent path patterns (A-14).

Patterns and paths are relative POSIX strings. ``**`` matches any number of segments (including none),
``*`` and ``?`` match within one segment, matching is case-sensitive on every platform.

Matching walks the pattern once over the set of reachable path positions, so the effort grows with
pattern length × path depth and stays bounded for hostile patterns (A-53).
"""

from __future__ import annotations

from fnmatch import fnmatchcase


def _segments(text: str) -> list[str]:
    return [part for part in text.strip("/").split("/") if part]


def match(pattern: str, path: str) -> bool:
    segments = _segments(path)
    reachable = [True] + [False] * len(segments)  # reachable[j]: the pattern so far matches path[:j]
    previous = None
    for part in _segments(pattern):
        if part == "**":
            if previous == "**":
                continue  # consecutive ** are one **
            seen = False
            for j in range(len(segments) + 1):
                seen = seen or reachable[j]
                reachable[j] = seen
        else:
            reachable = [False] + [
                reachable[j] and fnmatchcase(segments[j], part) for j in range(len(segments))
            ]
        previous = part
    return reachable[len(segments)]
