"""tools/strace_check.py (NG-N01, A-49): classification of strace lines of the offline evidence.

SYNTHETIC INPUT: no Linux run exists yet (D-09). The lines below are written by hand in the documented output
format of `strace -f -e trace=connect,sendto,sendmsg` (strace 6.x); they are replaced by real traces of the
first CI run (offline.yml, artifact offline-evidence-strace) for review, not as test data."""

from __future__ import annotations

from pathlib import Path

import pytest

import strace_check

LOOPBACK = [
    '1234  connect(5, {sa_family=AF_INET, sin_port=htons(9), sin_addr=inet_addr("127.0.0.1")}, 16) '
    "= -1 ECONNREFUSED",
    "1234  connect(6, {sa_family=AF_INET6, sin6_port=htons(9), sin6_flowinfo=htonl(0), "
    'inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = -1 ECONNREFUSED',
    "1240  connect(3, {sa_family=AF_INET6, sin6_port=htons(53), sin6_flowinfo=htonl(0), "
    'inet_pton(AF_INET6, "::ffff:127.0.0.53", &sin6_addr), sin6_scope_id=0}, 28) = -1 ENETUNREACH',
]
NETWORK = [
    '1301  connect(7, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("140.82.112.3")}, 16) '
    "= -1 ENETUNREACH",
    '1302  sendto(8, "\\x12\\x34"..., 33, MSG_NOSIGNAL, {sa_family=AF_INET, sin_port=htons(53), '
    'sin_addr=inet_addr("8.8.8.8")}, 16) = -1 ENETUNREACH (Network is unreachable)',
    "1303  connect(9, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), "
    'inet_pton(AF_INET6, "2001:db8::1", &sin6_addr), sin6_scope_id=0}, 28 <unfinished ...>',
    "1304  connect(10, {sa_family=AF_INET, sin_port=htons(80), ...}, 16) = -1 EINVAL",  # address not readable
]
LOCAL = [
    '1234  connect(4, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT',
    "1234  sendto(3, [{nlmsg_len=20, nlmsg_type=RTM_GETADDR}], 20, 0, {sa_family=AF_NETLINK, nl_pid=0, "
    "nl_groups=00000000}, 12) = 20",
    '1250  sendmsg(11, {msg_name=NULL, msg_namelen=0, msg_iov=[{iov_base="x", iov_len=1}], msg_iovlen=1}, 0) '
    "= 1",
    '1251  sendto(12, "data", 4, 0, NULL, 0) = 4',
]


def test_classification_of_each_kind() -> None:
    assert [strace_check.classify(line)[0] for line in LOOPBACK] == ["loopback"] * 3  # type: ignore[index]
    assert [strace_check.classify(line)[0] for line in NETWORK] == ["network"] * 4  # type: ignore[index]
    assert [strace_check.classify(line)[0] for line in LOCAL] == [
        "local",
        "local",
        "no-address",
        "no-address",
    ]  # type: ignore[index]
    assert strace_check.classify("1303  <... connect resumed>) = -1 ENETUNREACH") is None
    assert strace_check.classify("+++ exited with 0 +++") is None


def test_folder_with_only_local_and_loopback_calls_passes(tmp_path: Path) -> None:
    (tmp_path / "strace-check.txt").write_text("\n".join(LOCAL + LOOPBACK) + "\n", encoding="utf-8")
    (tmp_path / "strace-install.txt").write_text("\n".join(LOCAL) + "\n", encoding="utf-8")
    assert strace_check.main([str(tmp_path)]) == 0
    summary = (tmp_path / "strace-summary.txt").read_text(encoding="utf-8")
    assert "strace-check.txt: 7 calls, 0 network, 3 loopback" in summary
    assert summary.count("  loopback: ") == 3 and summary.endswith("result: no network attempt\n")


def test_any_non_loopback_address_fails(tmp_path: Path) -> None:
    (tmp_path / "strace-report.txt").write_text("\n".join(LOCAL + NETWORK) + "\n", encoding="utf-8")
    assert strace_check.main([str(tmp_path)]) == 1
    summary = (tmp_path / "strace-summary.txt").read_text(encoding="utf-8")
    assert summary.count("NETWORK: strace-report.txt: ") == 4 and "140.82.112.3" in summary


@pytest.mark.parametrize("args", [[], ["a", "b"]])
def test_usage_and_empty_folder_exit_2(tmp_path: Path, args: list[str]) -> None:
    assert strace_check.main(args) == 2
    assert strace_check.main([str(tmp_path)]) == 2
