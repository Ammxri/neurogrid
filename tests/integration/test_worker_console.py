"""Workers of ``--jobs`` never reach the console (G1 finding on dcec9bd; NG-N05, NG-N03, TECH-05, NG-F07).

In the G1 run, ``check --jobs 4`` on ds004504 printed ``Process SpawnProcess-2: Traceback ... queues.py,
in get: self._sem.release() OSError: [WinError 6] Das Handle ist ungültig`` to stderr (install paths with
the user name, German text in the console code page) and took three times as long: the pool broke and every
unfinished recording ran again on its own. Cause (kernel/processes.py, ``avoid_wmi``): CPython 3.12's WMI
query behind ``platform.uname()`` (reached in a worker through ``import scipy.signal``) gives up after
1000/100 ms while its thread keeps running on the returned call's stack data; that thread then closed a
handle value it read there: the semaphore of the worker's call queue. The tests:

- the race itself, made deterministic: the first worker's call-queue semaphore is closed while the worker
  waits in ``call_queue.get`` (Windows: the real handle, its value then names a pipe; elsewhere a semaphore
  whose release fails the same way). The worker dies exactly as in the G1 run; the console stays clean and
  the results equal one process;
- no pool worker asks WMI (audit event ``_wmi.exec_query``) when a library asks ``platform``;
- through the real CLI with ``--jobs 2``: workers that write at interpreter start (spawn) or right after
  the fork, at their bootstrap and at shutdown, and one that dies at ``call_queue.get``, leave stdout and
  stderr as the G1 acceptance demands (strict UTF-8, only translated lines, no traceback, no path, home
  folder or user name; tools/acceptance_g1.py), the CLI process asks no WMI either, and results.json is
  byte-identical to ``--jobs 1``. The dead worker is named once by NeuroGrid's own translated note.
"""

from __future__ import annotations

import errno
import importlib.util
import multiprocessing
import os
import platform
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # the helpers of test_quality_pipeline, also when run alone

from test_quality_pipeline import CAP_8, CAP_19, eeg_like, write_edf  # type: ignore[import-not-found,unused-ignore]  # noqa: E402

import acceptance_g1 as g1  # type: ignore[import-not-found]  # noqa: E402
from conftest import documented_config  # type: ignore[import-not-found,unused-ignore]  # noqa: E402
from neurogrid import quality  # noqa: E402
from neurogrid.io.edf import EdfAdapter  # noqa: E402
from neurogrid.quality import QualityJob, QualitySettings, workers  # noqa: E402
from neurogrid.report.texts import translator  # noqa: E402

CLOSE_ONCE = "NEUROGRID_TEST_CLOSE_QUEUE_SEMAPHORE"  # marker file: the first worker that creates it
WMI_SEEN = "NEUROGRID_TEST_WMI_SEEN"  # marker file: written when a worker calls _wmi.exec_query
HAS_WMI = importlib.util.find_spec("_wmi") is not None
CONSOLE_TRACES = ("Traceback", "SpawnProcess", "ForkProcess", "WinError", "Errno", 'File "', "queues.py")
_kept: list[int] = []  # handles that keep a closed value taken (Windows)


class _ClosedSemaphore:
    """A semaphore whose handle another part of the process has closed (POSIX stand-in)."""

    def release(self) -> None:
        raise OSError(errno.EBADF, os.strerror(errno.EBADF))


def _close_call_queue_semaphore() -> None:
    """In a pool worker: the semaphore of its call queue is closed, as CPython's WMI thread did."""
    call_queue = multiprocessing.current_process()._args[0]  # type: ignore[attr-defined]
    if sys.platform == "win32":
        import _winapi

        _winapi.CloseHandle(call_queue._sem._semlock.handle)
        _kept.extend(_winapi.CreatePipe(None, 0))  # the freed value names another object, as in G1
    else:
        call_queue._sem = _ClosedSemaphore()


def _start_and_close_once() -> None:
    """Pool initializer of the test: NeuroGrid's start-up, then the first worker loses its semaphore while
    it is about to wait in call_queue.get."""
    workers.worker_start()
    try:
        os.close(os.open(os.environ[CLOSE_ONCE], os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return
    _close_call_queue_semaphore()


def _start_and_ask_platform() -> None:
    """Pool initializer of the test: NeuroGrid's start-up, then a library asks platform (as numpy.testing
    does at its import, reached through scipy.signal); a WMI query is recorded."""
    marker = os.environ[WMI_SEEN]

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "_wmi.exec_query":
            os.close(os.open(marker, os.O_CREAT | os.O_WRONLY))

    sys.addaudithook(audit)
    workers.worker_start()
    platform.machine()


def _cheap_jobs(folder: Path) -> list[QualityJob]:
    jobs = []
    for i in range(3):
        path = write_edf(folder / f"rec_{i}.edf", CAP_8, eeg_like(CAP_8, 12, 256, 60 + i), 256)
        recording = EdfAdapter().read(path, recording_id=path.name, relative_path=path.name)
        jobs.append(QualityJob(path=str(path), recording=recording, settings=QualitySettings(), sample=False))
    return jobs


def test_a_worker_whose_call_queue_semaphore_is_closed_leaves_the_console_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """The G1 failure, deterministic: the worker dies at call_queue.get (WinError 6); before the fix its
    traceback with install paths reached the console (the full-suite log of dcec9bd shows it under
    'Captured stderr'). Now nothing does, and the jobs it took down give the values of one process."""
    jobs = _cheap_jobs(tmp_path)
    expected = [quality.compute(job) for job in jobs]
    marker = tmp_path / "closed"
    monkeypatch.setenv(CLOSE_ONCE, str(marker))
    monkeypatch.setattr(quality, "_worker_start", _start_and_close_once)
    capfd.readouterr()
    results = quality.compute_all(jobs, workers=2)
    out, err = capfd.readouterr()
    assert marker.exists()  # one worker really lost its semaphore
    assert results == expected
    assert (out, err) == ("", ""), [trace for trace in CONSOLE_TRACES if trace in out + err]


@pytest.mark.skipif(not HAS_WMI, reason="CPython's _wmi module (Windows, Python 3.12+)")
def test_no_pool_worker_asks_wmi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The root cause: a library in a worker asks platform after NeuroGrid's start-up; platform answers
    without _wmi.exec_query (whose timeout closed the call-queue semaphore in the G1 run)."""
    marker = tmp_path / "wmi"
    monkeypatch.setenv(WMI_SEEN, str(marker))
    monkeypatch.setattr(quality, "_worker_start", _start_and_ask_platform)
    jobs = _cheap_jobs(tmp_path)
    assert quality.compute_all(jobs, workers=2) == [quality.compute(job) for job in jobs]
    assert not marker.exists()


# --- through the real CLI -----------------------------------------------------------------------------------

# Loaded as sitecustomize through PYTHONPATH by the CLI process and (spawn) by every worker; with fork the
# workers inherit it from the CLI process. Markers: <marks>/<what>-<pid>.
HOOK = r"""
import os
import sys

MARKS = os.environ.get("NEUROGRID_TEST_MARKS")
if MARKS:

    def mark(name):
        os.close(os.open(os.path.join(MARKS, f"{name}-{os.getpid()}"), os.O_CREAT | os.O_WRONLY))

    def audit(event, args):
        if event == "_wmi.exec_query":
            mark("wmi")

    sys.addaudithook(audit)
    USER = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    NOISE = (
        "Traceback (most recent call last):\n  File \"" + os.path.join(os.path.expanduser("~"), "worker.py")
        + "\", line 1, in <module>\nOSError: [WinError 6] Das Handle ist ung\xfcltig (" + USER + ")\n"
    )

    def noise(where):
        mark(where)
        for fd in (1, 2):
            try:
                os.write(fd, NOISE.encode("cp1252", "replace"))  # a console code page: not UTF-8
            except OSError:
                pass
        try:
            print(NOISE, file=sys.stderr, flush=True)
        except Exception:
            pass

    if "--multiprocessing-fork" in sys.argv:  # a spawned worker, at interpreter start
        import atexit

        noise("start")
        atexit.register(noise, "exit")
    elif hasattr(os, "register_at_fork"):  # a forked worker, before multiprocessing's bootstrap
        os.register_at_fork(after_in_child=lambda: noise("start"))

    import concurrent.futures.process as futures_process

    original = futures_process._process_worker

    def _process_worker(call_queue, *args):
        from multiprocessing import util

        util.Finalize(None, noise, args=("shutdown",), exitpriority=0)
        try:
            os.close(os.open(os.path.join(MARKS, "closed"), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            pass
        else:  # the first worker loses the semaphore of its call queue, as in the G1 run
            mark("close")
            if sys.platform == "win32":
                import _winapi

                _winapi.CloseHandle(call_queue._sem._semlock.handle)
                globals()["kept"] = _winapi.CreatePipe(None, 0)
            else:

                class Closed:
                    def release(self):
                        raise OSError(9, "Bad file descriptor")

                call_queue._sem = Closed()
        return original(call_queue, *args)

    _process_worker.__module__ = original.__module__
    _process_worker.__qualname__ = original.__qualname__
    futures_process._process_worker = _process_worker
"""


def _run(arguments: list[str], cwd: Path, hook: Path, marks: Path) -> g1.CommandRun:
    """``neurogrid`` as the customer runs it (tools/acceptance_g1.py), with the hook loaded."""
    env = g1.child_environment("en")
    env["PYTHONPATH"] = str(hook)
    env["NEUROGRID_TEST_MARKS"] = str(marks)
    start = time.perf_counter()
    done = subprocess.run(
        [str(g1.neurogrid_executable()), *arguments], cwd=cwd, env=env, capture_output=True, check=False
    )
    return g1.CommandRun(arguments[0], done.returncode, done.stdout, done.stderr, time.perf_counter() - start)


def _measured(jobs: int, run: g1.CommandRun, problems: list[str], tmp_path: Path) -> str:
    """The assertion message on one line (CI annotates the first line of a failure): the problems and the
    console lines behind them, i.e. every stderr line that is no translated library warning and every stdout
    line with a trace, the home folder, the user or the host name; those three and the test folder are
    replaced by placeholders, each line is cut."""
    names = {os.environ.get(key, "") for key in ("USERNAME", "USER", "LOGNAME")}
    replacements = [(str(tmp_path), "<tmp>"), (str(Path.home()), "<home>")]
    replacements += [(name, "<user>") for name in sorted(names) if len(name) >= 3]
    host = socket.gethostname()
    replacements += [(host, "<host>")] if len(host) >= 3 else []
    warning = g1._library_warning("en")

    def clean(line: str) -> str:
        for value, mark in replacements:
            line = re.sub(re.escape(value), mark, line, flags=re.IGNORECASE)
        return line[:140]

    shown = []
    for stream, data in (("stderr", run.stderr), ("stdout", run.stdout)):
        for line in data.decode("utf-8", "replace").splitlines():
            line = clean(line.strip())
            if not line:
                continue
            if stream == "stderr" and not warning.fullmatch(line):
                shown.append(f"stderr: {line}")
            elif stream == "stdout" and any(
                mark in line for mark in (*CONSOLE_TRACES, "<home>", "<user>", "<host>")
            ):
                shown.append(f"stdout: {line}")
    return f"--jobs {jobs}, exit {run.code}: {problems} {shown[:4]!r}"


def test_the_failure_message_shows_the_offending_console_lines(tmp_path: Path) -> None:
    """The message of the console assertions below names what was measured, without the home folder."""
    warning = translator("en").t("cli.warning.library", type="RuntimeWarning").encode("utf-8")
    trace = f'Traceback (most recent call last):\n  File "{Path.home() / "x.py"}", line 1'.encode()
    run = g1.CommandRun("check", 1, b"done\n" + trace + b"\n", warning + b"\n[W:onnxruntime] GPU\n", 0.0)
    message = _measured(1, run, ["stderr holds a line that is no translated NeuroGrid message"], tmp_path)
    assert message.startswith("--jobs 1, exit 1: ['stderr holds a line")
    assert "'stderr: [W:onnxruntime] GPU'" in message and "stdout: Traceback" in message
    assert f'stdout: File "<home>{os.sep}x.py"'.replace("\\", "\\\\") in message
    assert "\n" not in message and str(Path.home()) not in message and "cli.warning" not in message


def test_check_with_jobs_keeps_the_console_clean_when_workers_write_and_die(tmp_path: Path) -> None:
    """G1 console and privacy checks on check --jobs 2 whose workers write at start, bootstrap and shutdown
    and one of which dies at call_queue.get; results.json equals --jobs 1 (which computes in the CLI
    process); no process asks WMI. The death shows only as NeuroGrid's note on stdout (A-89). The console
    checks hold for --jobs 1 too: on Linux (18da12f) its run failed them, the message showed only "1";
    onnxruntime's Linux build logs its device discovery to descriptor 2 (quality.sample, on_null_device)."""
    dataset = tmp_path / "data"
    write_edf(dataset / "rest_a.edf", CAP_19, eeg_like(CAP_19, 64, 250, 71), 250)  # sample-capable
    write_edf(dataset / "rest_b.edf", CAP_8, eeg_like(CAP_8, 20, 256, 72), 256)
    config = documented_config(tmp_path)
    hook = tmp_path / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
    marks = tmp_path / "marks"
    marks.mkdir()
    out = {jobs: tmp_path / f"jobs{jobs}" / "results.json" for jobs in (1, 2)}
    arguments = ["check", str(dataset), "--config", str(config), "--as-of", g1.AS_OF.isoformat()]
    for path in out.values():
        path.parent.mkdir()
    with ThreadPoolExecutor(max_workers=2) as both:  # --jobs 1 and --jobs 2 at the same time
        started = {
            jobs: both.submit(
                _run, [*arguments, "--jobs", str(jobs), "--out", str(path)], tmp_path, hook, marks
            )
            for jobs, path in out.items()
        }
        runs = {jobs: future.result() for jobs, future in started.items()}
    forbidden = g1.forbidden_values(dataset, tmp_path)
    for jobs, run in runs.items():
        assert run.code in (0, 1), (jobs, run.stderr.decode("utf-8", "replace"))
        problems = g1.check_console(run.stdout, run.stderr, "en", run.code, allowed_paths=(tmp_path,))
        assert problems == [], _measured(jobs, run, problems, tmp_path)
        leaks = g1.check_privacy([g1.console_output("check", run, tmp_path)], forbidden, None)
        assert leaks == [], _measured(jobs, run, leaks, tmp_path)
    assert runs[1].code == runs[2].code
    assert out[2].read_bytes() == out[1].read_bytes()  # NG-N03, also after the worker died
    marker = "\x00"
    note = re.compile(
        re.escape(translator("en").t("cli.check.recomputed", count=marker)).replace(marker, r"[1-9]\d*")
    )
    notes = {
        jobs: [line for line in run.stdout.decode("utf-8").splitlines() if note.fullmatch(line)]
        for jobs, run in runs.items()
    }
    assert (len(notes[1]), len(notes[2])) == (0, 1), notes
    seen = {path.name.rsplit("-", 1)[0] for path in marks.iterdir()}
    assert {"start", "close", "shutdown"} <= seen  # the workers did write, one did lose its semaphore
    assert "wmi" not in seen  # neither the CLI process (--jobs 1 computes the sample) nor a worker
