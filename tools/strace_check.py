"""Evaluate strace output of the offline evidence (NG-N01, CON-04, ARC-06, A-49; CI, D-09).

Reads every strace-*.txt in an evidence folder (written by `strace -f -e trace=connect,sendto,sendmsg`) and
classifies each call by the address family it names:
  - AF_INET / AF_INET6 with a non-loopback address: a network attempt -> listed, exit 1;
  - AF_INET / AF_INET6 with a loopback address (127.0.0.0/8, ::1, ::ffff:127.x): allowed, counted and listed,
    except port 9 (discard), the port of a dead proxy such as http://127.0.0.1:9: a client that honours proxy
    variables sends its phone-home there instead of resolving the real host, so it is a network attempt;
  - AF_UNIX, AF_NETLINK or no address (connected socket, pipe-like socket pair): counted.
An AF_INET/AF_INET6 call whose address cannot be read is treated as a network attempt.
Writes strace-summary.txt into the folder (and never reads it back as a trace). Standard library only; runs
with the system Python of the runner.

Usage: python3 tools/strace_check.py EVIDENCE_DIR
Exit codes: 0 no network attempt, 1 network attempts found, 2 no trace files or usage error.
"""

from __future__ import annotations

import ipaddress
import re
import sys
from collections import Counter
from pathlib import Path

CALL = re.compile(r"\b(connect|sendto|sendmsg)\(")
FAMILY = re.compile(r"sa_family=(AF_[A-Z0-9]+)")
IPV4 = re.compile(r'inet_addr\("([^"]*)"\)')
IPV6 = re.compile(r'inet_pton\(AF_INET6, "([^"]*)"')
PORT = re.compile(r"\bsin6?_port=htons\((\d+)\)")
DEAD_PROXY_PORTS = frozenset({9})  # discard: where a dead proxy points; nothing legitimate connects there
SUMMARY = "strace-summary.txt"


def is_loopback(text: str) -> bool:
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(address.is_loopback or (mapped is not None and mapped.is_loopback))


def classify(line: str) -> tuple[str, str] | None:
    """(kind, detail) of one strace line; None for lines that are no traced call (e.g. '<... resumed>')."""
    call = CALL.search(line)
    if call is None:
        return None
    family = FAMILY.search(line)
    if family is None:
        return "no-address", call.group(1)
    name = family.group(1)
    if name not in ("AF_INET", "AF_INET6"):
        return "local", name
    found = (IPV4 if name == "AF_INET" else IPV6).search(line)
    if found is None:
        return "network", line.strip()
    if not is_loopback(found.group(1)):
        return "network", line.strip()
    port = PORT.search(line)
    if port is not None and int(port.group(1)) in DEAD_PROXY_PORTS:
        return "network", line.strip()  # a request handed to a dead proxy on this machine
    return "loopback", line.strip()


def check(folder: Path) -> tuple[list[str], list[str]]:
    """Summary lines and the network attempts of every trace file in ``folder``."""
    traces = sorted(path for path in folder.glob("strace-*.txt") if path.name != SUMMARY)
    if not traces:
        raise FileNotFoundError(f"no strace-*.txt in {folder}")
    summary: list[str] = []
    attempts: list[str] = []
    for trace in traces:
        counts: Counter[str] = Counter()
        loopback: list[str] = []
        for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
            result = classify(line)
            if result is None:
                continue
            kind, detail = result
            counts[kind] += 1
            if kind == "loopback":
                loopback.append(detail)
            elif kind == "network":
                attempts.append(f"{trace.name}: {detail}")
        summary.append(
            f"{trace.name}: {sum(counts.values())} calls, {counts['network']} network, "
            f"{counts['loopback']} loopback, {counts['local']} local (AF_UNIX/AF_NETLINK), "
            f"{counts['no-address']} without address"
        )
        summary += [f"  loopback: {line}" for line in loopback]
    return summary, attempts


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__.split("\n\n")[-2], file=sys.stderr)
        return 2
    folder = Path(args[0])
    try:
        summary, attempts = check(folder)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    verdict = "no network attempt" if not attempts else f"{len(attempts)} network attempt(s)"
    lines = [*summary, *(f"NETWORK: {a}" for a in attempts), f"result: {verdict}"]
    (folder / SUMMARY).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 1 if attempts else 0


if __name__ == "__main__":
    sys.exit(main())
