"""Processes NeuroGrid starts never write to the console (kernel/processes.py; NG-N05, A-51, TECH-05).

- Start layer: a pool on ``pool_context`` (every start method of the platform) starts its processes on the
  null device: what a worker writes before any NeuroGrid code runs (an initializer that prints, a task
  that writes to its descriptors, raises, or starts a process of its own) never reaches this process's
  console streams, and the results are unchanged.
- Initializer layer: ``to_null_device`` alone also silences a worker of a plain multiprocessing context and
  the processes that worker starts; in NeuroGrid's own process it changes nothing.
- ``avoid_wmi``: ``platform`` answers without WMI (CPython 3.12's ``_wmi.exec_query`` closes foreign
  handles when it times out).
"""

from __future__ import annotations

import gc
import multiprocessing
import os
import subprocess
import sys
import weakref
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.context import BaseContext
from pathlib import Path

import pytest

from neurogrid.kernel import processes

METHODS = multiprocessing.get_all_start_methods()
NOISE = 'Traceback (most recent call last):\n  File "C:\\Users\\someone\\x.py", line 1\nOSError: x\n'


def _noisy_start() -> None:
    """An initializer that writes everywhere before (and without) NeuroGrid's own start-up."""
    print(NOISE, flush=True)
    print(NOISE, file=sys.stderr, flush=True)
    os.write(1, NOISE.encode("utf-8"))
    os.write(2, b"ung\xfcltig " + NOISE.encode("utf-8"))  # text in a console code page: not UTF-8


def _quiet_then_noisy_start() -> None:
    processes.to_null_device()
    _noisy_start()


def _noisy_task(value: int) -> int:
    os.write(2, NOISE.encode("utf-8"))
    print(NOISE, file=sys.stderr)
    if value == 2:
        raise RuntimeError(NOISE)
    if value == 3:  # a process the worker starts itself inherits its console
        child = f"import sys; print({NOISE!r}); print({NOISE!r}, file=sys.stderr)"
        subprocess.run([sys.executable, "-c", child], check=True)
    return value * 10


def _run_pool(context: BaseContext, initializer: Callable[[], None]) -> list[object]:
    out: list[object] = []
    with ProcessPoolExecutor(max_workers=2, mp_context=context, initializer=initializer) as pool:
        for future in [pool.submit(_noisy_task, value) for value in range(5)]:
            try:
                out.append(future.result())
            except RuntimeError as exc:
                out.append(type(exc).__name__)
    return out


@pytest.mark.parametrize("method", METHODS)
def test_pool_processes_start_on_the_null_device(method: str, capfd: pytest.CaptureFixture[str]) -> None:
    """Nothing of the initializer, the tasks or their own child process reaches the console: the start
    layer alone (the initializer does not call to_null_device)."""
    results = _run_pool(processes.pool_context(method), _noisy_start)
    out, err = capfd.readouterr()
    assert results == [0, 10, "RuntimeError", 30, 40]
    assert (out, err) == ("", "")


@pytest.mark.parametrize("method", METHODS)
def test_the_initializer_alone_silences_a_worker_and_its_children(
    method: str, capfd: pytest.CaptureFixture[str]
) -> None:
    """A plain multiprocessing context inherits the console; to_null_device as the first step of the
    initializer still keeps the worker and the process it starts off the console."""
    results = _run_pool(multiprocessing.get_context(method), _quiet_then_noisy_start)
    out, err = capfd.readouterr()
    assert results == [0, 10, "RuntimeError", 30, 40]
    assert (out, err) == ("", "")


def test_without_either_layer_the_worker_writes_to_the_console(capfd: pytest.CaptureFixture[str]) -> None:
    """The counter-check of the two tests above: a plain context and a plain initializer reach the
    console (this is what the G1 run showed)."""
    _run_pool(multiprocessing.get_context(METHODS[0]), _noisy_start)
    out, err = capfd.readouterr()
    assert "Traceback" in out + err


def test_to_null_device_keeps_the_console_of_neurogrids_own_process() -> None:
    streams = (sys.stdin, sys.stdout, sys.stderr)
    processes.to_null_device()
    assert (sys.stdin, sys.stdout, sys.stderr) == streams


def test_pool_context_follows_the_start_method() -> None:
    assert processes.pool_context().get_start_method() == processes.default_start_method()
    for method in METHODS:
        context = processes.pool_context(method)
        assert context.get_start_method() == method
        assert context is processes.pool_context(method)
    with pytest.raises(ValueError, match="unsupported start method"):
        processes.pool_context("teleport")


def test_quiet_pool_leaves_the_call_queue_collectable() -> None:
    """The feeder error handler that quiet_pool installs refers to the call queue weakly: a dropped queue is
    collected and its finalizer stops the feeder thread (a strong reference from that thread kept both)."""
    pool = processes.quiet_pool(ProcessPoolExecutor(max_workers=1, mp_context=processes.pool_context()))
    call_queue = pool._call_queue  # type: ignore[attr-defined]
    call_queue.put(None)  # starts the feeder thread; the pipe takes it, no worker reads
    feeder, queue_ref = call_queue._thread, weakref.ref(call_queue)
    pool.shutdown()
    del pool, call_queue
    gc.collect()
    feeder.join(timeout=60)
    assert queue_ref() is None
    assert not feeder.is_alive()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX descriptors")
def test_null_descriptors_restore_open_and_closed_descriptors(tmp_path: Path) -> None:
    """While a child starts, 0-2 are the null device; afterwards the same files again, and a descriptor
    that was closed is closed again."""
    script = tmp_path / "probe.py"
    script.write_text(
        "import os, sys\n"
        "from neurogrid.kernel import processes\n"
        "before = os.fstat(1).st_ino\n"
        "with processes.null_descriptors():\n"
        "    inside = os.fstat(1).st_ino, os.fstat(0).st_ino\n"
        "assert os.fstat(1).st_ino == before, 'stdout restored'\n"
        "try:\n"
        "    os.fstat(0)\n"
        "    print('open')\n"
        "except OSError:\n"
        "    print('closed')\n"
        "assert inside[0] == inside[1] == os.stat(os.devnull).st_ino\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, str(script)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert done.stdout.strip() == "open"
    closed = subprocess.run(
        ["/bin/sh", "-c", f'"{sys.executable}" "{script}" <&-'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert closed.stdout.strip() == "closed"


@pytest.mark.skipif(sys.platform != "win32", reason="CPython's _wmi exists on Windows only")
def test_avoid_wmi_keeps_platform_answering_without_a_wmi_query() -> None:
    """After avoid_wmi, platform.uname() and platform.machine() answer (from ver and the environment, as
    before CPython 3.12) and _wmi.exec_query is never called (audit event)."""
    code = (
        "import sys\n"
        "seen = []\n"
        "sys.addaudithook(lambda event, args: seen.append(event) if event == '_wmi.exec_query' else None)\n"
        "from neurogrid.kernel import processes\n"
        "processes.avoid_wmi()\n"
        "import platform\n"
        "uname = platform.uname()\n"
        "assert uname.system == 'Windows' and uname.release and uname.version, uname\n"
        "assert platform.machine(), 'machine'\n"
        "print(len(seen))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", check=True
    )
    assert done.stdout.strip() == "0"


NAMED = [method for method in METHODS if method != "fork"]  # their semaphores are named (POSIX)
_KILLED_WITH_A_POOL = """
import multiprocessing, os, signal, sys
from concurrent.futures import ProcessPoolExecutor
method, quiet = sys.argv[1], sys.argv[2] == "quiet"
multiprocessing.set_start_method(method)
if quiet:
    from neurogrid import quality
    pool = quality._pool(2)  # as compute_all creates it
else:
    pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context(method))
print(pool._call_queue._sem._semlock.name, flush=True)
os.kill(os.getpid(), signal.SIGKILL)  # no finalizer runs: the semaphores are left to the tracker
"""


def _killed_with_a_pool(method: str, how: str) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONWARNDEFAULTENCODING", "PYTHONWARNINGS")}
    return subprocess.run(
        [sys.executable, "-c", _KILLED_WITH_A_POOL, method, how],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=env,
        timeout=180,
        check=False,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX: multiprocessing's resource tracker")
@pytest.mark.parametrize("method", NAMED)
def test_the_resource_tracker_of_a_pool_has_no_console(method: str) -> None:
    """spawn and forkserver: a pool's semaphores register with multiprocessing's resource tracker, which
    ProcessPoolExecutor.__init__ would start with the console. NeuroGrid's process is killed while the pool
    exists (SIGKILL: no finalizer): the tracker still cleans up, but its 'leaked semaphore objects' warning
    with its install path goes to the null device. Counter-check: a plain pool's tracker prints it."""
    import signal

    plain = _killed_with_a_pool(method, "plain")
    assert plain.returncode == -signal.SIGKILL
    assert b"leaked semaphore" in plain.stderr, plain.stderr.decode("utf-8", "replace")
    done = _killed_with_a_pool(method, "quiet")
    assert done.returncode == -signal.SIGKILL, done.stderr.decode("utf-8", "replace")
    assert done.stderr == b"", done.stderr.decode("utf-8", "replace")
    name = done.stdout.decode("ascii").strip()
    assert name.startswith("/")
    if Path("/dev/shm").is_dir():  # Linux: the tracker did unlink the semaphore
        assert not Path("/dev/shm", "sem." + name[1:]).exists()
