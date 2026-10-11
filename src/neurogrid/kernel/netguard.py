"""Network guard for the Python process (A-49).

An audit hook blocks socket connections, datagrams and every kind of name resolution (getaddrinfo,
gethostbyname[_ex], gethostbyaddr, getnameinfo) towards non-loopback addresses.

Limits, stated openly: it only covers this Python process – subprocesses are restricted by their own
flags – and asyncio's Windows proactor connects without an audit event. NeuroGrid uses no asyncio
networking; a source test forbids network APIs (tests/unit/test_architecture.py).
"""

from __future__ import annotations

import ipaddress
import socket
import sys

from neurogrid.kernel.errors import NetworkBlockedError

_state = {"installed": False, "blocked": 0}
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


def _is_local(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    name = host.strip().strip("[]").lower()
    if name in ("", *_LOCAL_NAMES):
        return True
    try:
        address = ipaddress.ip_address(name.split("%")[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(address.is_loopback or (mapped is not None and mapped.is_loopback))


def _host_of(address: object) -> object:
    if isinstance(address, tuple) and address:
        return address[0]
    if isinstance(address, (str, bytes)):
        return address
    return None


def _hook(event: str, args: tuple[object, ...]) -> None:
    if event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        sock, address = args[0], args[1]
        if getattr(sock, "family", None) == getattr(socket, "AF_UNIX", object()):
            return
        if address is None:  # sendmsg on an already connected socket; the connect was checked
            return
        host = _host_of(address)
    elif event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"):
        host = args[0]
    elif event == "socket.getnameinfo":
        host = _host_of(args[0])
    else:
        return
    if not _is_local(host):
        _state["blocked"] += 1
        raise NetworkBlockedError("network access is disabled in NeuroGrid")


def install() -> None:
    """Install the hook once per process. Audit hooks cannot be removed again."""
    if not _state["installed"]:
        sys.addaudithook(_hook)
        _state["installed"] = True


def blocked_count() -> int:
    return _state["blocked"]
