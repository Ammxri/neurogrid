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

import importlib.util
import json
import multiprocessing
import os
import select
import subprocess
import sys
import time
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


FAILING_WINDOW = """
import errno, json, os, sys
from neurogrid.kernel import processes

scenario, report = sys.argv[1], sys.argv[2]
real_open = os.open
copies = []


def files():
    found = {}
    for fd in range(256):
        try:
            st = os.fstat(fd)
        except OSError:
            continue
        found[fd] = (st.st_dev, st.st_ino, os.get_inheritable(fd))
    return found


def copied(*args):  # the copy of a console descriptor: F_DUPFD_CLOEXEC (POSIX) or os.dup (Windows)
    if scenario == "copy" and copies:  # the second copy finds no free descriptor
        raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))
    copies.append(real_copy(*args))
    return copies[-1]


def failing_open(path, flags, *args, **kwargs):
    if scenario == "null" and path == os.devnull:
        raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))
    return real_open(path, flags, *args, **kwargs)


if sys.platform == "win32":
    real_copy = real_dup = os.dup
else:
    import fcntl

    real_copy = real_fcntl = fcntl.fcntl

    def failing_fcntl(fd, command, argument=0):
        if command == fcntl.F_DUPFD_CLOEXEC:
            return copied(fd, command, argument)
        return real_fcntl(fd, command, argument)

before = files()
os.open = failing_open
if sys.platform == "win32":
    os.dup = copied
else:
    fcntl.fcntl = failing_fcntl
ran, raised = False, None
try:
    with processes.on_null_device():
        ran = True
except OSError as error:
    raised = errno.errorcode.get(error.errno)
os.open = real_open
if sys.platform == "win32":
    os.dup = real_dup
else:
    fcntl.fcntl = real_fcntl
listed = getattr(processes, "_SAVED", [])
result = {"raised": raised, "ran": ran, "listed": listed, "copies": len(copies)}
result["unchanged"] = files() == before
with open(report, "w", encoding="utf-8") as out:
    json.dump(result, out)
"""


@pytest.mark.parametrize("scenario", ["copy", "null"])
def test_a_window_that_runs_out_of_descriptors_changes_nothing(scenario: str, tmp_path: Path) -> None:
    """EMFILE while on_null_device (POSIX: null_descriptors) saves a console descriptor ("copy") or opens
    the null device ("null"): it raises before the block, every copy is closed and none stays listed, and
    every descriptor is the same file with the same flag. Before, on POSIX "null" left the copies open and
    listed in _SAVED, so that every later fork of the process closed those numbers in the child and rebound
    its sys streams, and "copy" took the open descriptor for a closed one, ran the block and closed the
    console descriptor afterwards; on Windows the block ran as it was."""
    script, report = tmp_path / "probe.py", tmp_path / "report.json"
    script.write_text(FAILING_WINDOW, encoding="utf-8")
    subprocess.run(
        [sys.executable, str(script), scenario, str(report)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=True,
    )
    result = json.loads(report.read_text(encoding="utf-8"))
    expected = {"raised": "EMFILE", "ran": False, "listed": [], "unchanged": True}
    assert {key: result[key] for key in expected} == expected and result["copies"] >= 1, result


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX descriptors and fork")
def test_null_descriptors_cover_a_stream_on_another_descriptor_and_a_forked_child(tmp_path: Path) -> None:
    """sys.stdout on a copy of the console (descriptor above 2, as under pytest's capfd or in an embedding
    program): while a child starts, writes through it reach the null device, in this process and in a
    child forked meanwhile. That child writes through sys streams on the null device, holds no descriptor
    of the console, and the copy keeps its inheritance flag. Before, the forked pool worker's traceback
    reached capfd (test_pool_processes_start_on_the_null_device[fork] on Linux, 18da12f)."""
    script = tmp_path / "probe.py"
    script.write_text(
        "import os, sys\n"
        "from neurogrid.kernel import processes\n"
        "console = os.fstat(1)\n"
        "copy = os.dup(1)\n"
        "flag = os.get_inheritable(copy)\n"
        "old = sys.stdout = open(copy, 'w', encoding='utf-8')\n"
        "with processes.null_descriptors():\n"
        "    print('parent inside', flush=True)\n"
        "    pid = os.fork()\n"
        "    if pid == 0:\n"
        "        old.write('child through the old stream\\n')\n"
        "        old.flush()\n"
        "        print('child through sys.stdout', flush=True)\n"
        "        held = []\n"
        "        for fd in range(1024):\n"
        "            try:\n"
        "                st = os.fstat(fd)\n"
        "            except OSError:\n"
        "                continue\n"
        "            if (st.st_dev, st.st_ino) == (console.st_dev, console.st_ino):\n"
        "                held.append(fd)\n"
        "        rebound = sys.stdout is not old and sys.stdout.fileno() == 1\n"
        "        os._exit(2 * len(held) + (0 if rebound else 1))\n"
        "    _, status = os.waitpid(pid, 0)\n"
        "print('after', os.waitstatus_to_exitcode(status), os.get_inheritable(copy) == flag, flush=True)\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, str(script)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=True,
    )
    # child exit 0: no console descriptor held (2 per descriptor) and sys.stdout rebound (1 if not)
    assert done.stdout == "after 0 True\n", (done.stdout, done.stderr)


def test_on_null_device_keeps_native_output_of_library_code_off_the_console(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """In NeuroGrid's own process (--jobs 1): what library code writes to descriptors 1 and 2 inside
    on_null_device (onnxruntime's Linux build logs this line when it creates its environment) and through
    the sys streams (here capfd's, on other descriptors) reaches nothing; afterwards the console is back.
    Before, on Windows the block ran as it was and all of it reached capfd."""
    line = b"[W:onnxruntime:Default, device_discovery.cc] GPU device discovery failed: Failed to open file\n"
    capfd.readouterr()
    with processes.on_null_device():
        os.write(2, line)
        os.write(1, line)
        print(NOISE, flush=True)
        print(NOISE, file=sys.stderr, flush=True)
    os.write(2, b"after\n")
    print("after", flush=True)
    assert capfd.readouterr() == ("after\n", "after\n")


ONNXRUNTIME_LOG = """
import os, sys
import onnxruntime
from neurogrid.kernel import processes


def session():
    options = onnxruntime.SessionOptions()
    options.log_severity_level = 0
    onnxruntime.InferenceSession(sys.argv[1], options, providers=["CPUExecutionProvider"])


os.write(2, b"<inside>")
with processes.on_null_device():
    onnxruntime.set_default_logger_severity(0)  # every line from now on, also of the environment
    session()
os.write(2, b"<outside>")
session()
"""


def test_onnxruntime_logs_nothing_to_the_console_inside_on_null_device(tmp_path: Path) -> None:
    """onnxruntime's own logger, made to log every line (severity VERBOSE), writes them to stderr when it
    creates a session outside on_null_device and nothing inside it: the real native path of ICLabel's
    log lines, which on Windows goes through the C runtime that onnxruntime shares with Python (ucrtbase).
    Before, on Windows the session inside wrote its lines to stderr as well."""
    spec = importlib.util.find_spec("mne_icalabel")
    assert spec is not None and spec.origin is not None
    model = Path(spec.origin).parent / "iclabel" / "network" / "assets" / "ICLabelNet.onnx"
    script = tmp_path / "probe.py"
    script.write_text(ONNXRUNTIME_LOG, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(script), str(model)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=300,
        check=True,
    )
    err = done.stderr.replace(b"\x00", b"")  # the Windows build writes UTF-16 (std::wclog)
    inside = err.partition(b"<inside>")[2].partition(b"<outside>")[0]
    outside = err.partition(b"<outside>")[2]
    assert (inside, b"inference_session" in outside) == (b"", True), (inside[:300], outside[:300])


CONSOLE_PROBE = """
import ctypes, json, msvcrt, os, sys
from ctypes import wintypes
from neurogrid.kernel import processes


class Info(ctypes.Structure):
    _fields_ = [
        ("size", wintypes._COORD),
        ("cursor", wintypes._COORD),
        ("attributes", wintypes.WORD),
        ("window", wintypes.SMALL_RECT),
        ("maximum", wintypes._COORD),
    ]


def screen():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Info)]
    kernel32.ReadConsoleOutputCharacterW.argtypes = [
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes._COORD, ctypes.POINTER(wintypes.DWORD)
    ]
    handle, info, read = msvcrt.get_osfhandle(1), Info(), wintypes.DWORD()
    if not kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
        return f"no screen buffer: {ctypes.get_last_error()}"
    count = info.size.X * (info.cursor.Y + 1)
    text = ctypes.create_unicode_buffer(count + 1)
    kernel32.ReadConsoleOutputCharacterW(handle, text, count, wintypes._COORD(0, 0), ctypes.byref(read))
    return text.value[: read.value]


result = {"stream": type(getattr(sys.stdout, "buffer", sys.stdout).raw).__name__, "errors": []}
with processes.on_null_device():
    for write in (
        lambda: print("inside-out", flush=True),
        lambda: print("inside-err", file=sys.stderr, flush=True),
        lambda: os.write(1, b"inside-fd1 "),
        lambda: os.write(2, b"inside-fd2 "),
    ):
        try:
            write()
        except OSError as error:
            result["errors"].append(repr(error))
print("after-out", flush=True)
print("after-err", file=sys.stderr, flush=True)
text = screen()
result["inside"] = "inside" in text
result["after"] = "after-out" in text and "after-err" in text
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump(result, out)
"""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console streams (_WindowsConsoleIO)")
def test_on_null_device_on_a_windows_console_writes_nothing_there_and_raises_nothing(tmp_path: Path) -> None:
    """NeuroGrid run in a console window (--jobs 1): sys.stdout and sys.stderr are console streams, which
    raise OSError when their descriptor is on the null device. Inside on_null_device neither a print nor a
    write to descriptors 1 and 2 reaches the console or raises (an exception there would end ICLabel as
    failed: a value that depends on the console); afterwards both streams write to the console again. The
    console is a new one without a window (CREATE_NO_WINDOW); the probe reads its screen buffer. Before,
    all four writes inside reached the console."""
    script, report = tmp_path / "probe.py", tmp_path / "report.json"
    script.write_text(CONSOLE_PROBE, encoding="utf-8")
    subprocess.run(
        [sys.executable, str(script), str(report)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=120,
        check=True,
    )
    result = json.loads(report.read_text(encoding="utf-8"))
    expected = {"stream": "_WindowsConsoleIO", "errors": [], "inside": False, "after": True}
    assert result == expected, result


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
from multiprocessing import resource_tracker
method, quiet = sys.argv[1], sys.argv[2] == "quiet"
multiprocessing.set_start_method(method)
if quiet:
    from neurogrid import quality
    pool = quality._pool(2)  # as compute_all creates it
else:
    pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context(method))
print(pool._call_queue._sem._semlock.name, resource_tracker._resource_tracker._pid, flush=True)
os.kill(os.getpid(), signal.SIGKILL)  # no finalizer runs: the semaphores are left to the tracker
"""


def _wait_for_end(pid: int, timeout: float) -> tuple[bool, float]:
    """Waits up to ``timeout`` s for process ``pid``, which is no child of this one, to end; whether it
    ended and the seconds waited. Linux: a pidfd turns readable when the process has ended."""
    start = time.monotonic()
    pidfd_open = getattr(os, "pidfd_open", None)
    if pidfd_open is not None:
        try:
            fd = pidfd_open(pid)
        except ProcessLookupError:
            return True, time.monotonic() - start
        try:
            ready, _, _ = select.select([fd], [], [], timeout)
        finally:
            os.close(fd)
        return bool(ready), time.monotonic() - start
    while time.monotonic() - start < timeout:  # other POSIX systems: no pidfd
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True, time.monotonic() - start
        time.sleep(0.05)
    return False, time.monotonic() - start


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
    with its install path goes to the null device. Counter-check: a plain pool's tracker prints it.

    The plain run returns only when its tracker has cleaned up: the tracker holds the stderr pipe until it
    exits. The quiet tracker holds no pipe, so the run returns at the kill, while the tracker may still be
    starting; the test waits for its end before it looks for the semaphore."""
    import signal

    plain = _killed_with_a_pool(method, "plain")
    assert plain.returncode == -signal.SIGKILL
    assert b"leaked semaphore" in plain.stderr, plain.stderr.decode("utf-8", "replace")
    done = _killed_with_a_pool(method, "quiet")
    assert done.returncode == -signal.SIGKILL, done.stderr.decode("utf-8", "replace")
    assert done.stderr == b"", done.stderr.decode("utf-8", "replace")
    name, tracker = done.stdout.decode("ascii").split()
    assert name.startswith("/")
    ended, waited = _wait_for_end(int(tracker), timeout=60)
    assert ended, f"the resource tracker (pid {tracker}) still runs {waited:.1f} s after the kill"
    if Path("/dev/shm").is_dir():  # Linux: the tracker did unlink the semaphore
        left = Path("/dev/shm", "sem." + name[1:]).exists()
        assert not left, f"{name} still in /dev/shm after its tracker (pid {tracker}) ended ({waited:.2f} s)"
