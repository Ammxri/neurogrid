"""Processes that NeuroGrid starts for a computation never write to the console (NG-N05, A-51).

The console shows only NeuroGrid's translated messages. A worker behind ``--jobs`` runs library code and
the start-up code of multiprocessing, which print warnings and, when a worker fails, ``Process
SpawnProcess-N:`` with a traceback: install paths with the user name, text in the console code page. Two
layers keep every such line off the console:

- **Start:** the processes of NeuroGrid's pools (``pool_context``) start with the null device as stdin,
  stdout and stderr. On Windows the process is created with these three handles (STARTUPINFO; this handle
  is the only one it inherits). On POSIX this process points its descriptors 0-2 at the null device while
  it starts the child; fork, spawn and the forkserver (with its children) inherit them. Its pending output
  is written to the console before. From its first instruction on, nothing a worker writes reaches the
  console: interpreter start, unpickling of its start data, the bootstrap of multiprocessing and its
  error output. With spawn and forkserver ``pool_context`` also starts multiprocessing's resource tracker
  that way, before a pool's first semaphore would start it with the console.
- **Initializer:** ``to_null_device`` is the first step of every initializer (pool and loky workers). It
  points descriptors 0-2 and the sys streams at the null device again, so that the processes such a worker
  starts itself (loky's workers and resource tracker) inherit the null device as well.

What the parent needs from a worker reaches it through the pool: values, exceptions as data and the death
of a worker (BrokenProcessPool), which ``check`` names in a translated note (``quality.compute_all``,
``on_recompute``). The pool's own thread in NeuroGrid's process that feeds the workers prints nothing
either (``quiet_pool``). ``--debug`` changes nothing here; its cleaned traceback is that of NeuroGrid's own
process (A-51).

Not covered: output that a library writes to the console device itself (Windows ``CONOUT$`` or
``msvcrt.putwch``, POSIX ``/dev/tty``). The workers stay attached to the console (no CREATE_NO_WINDOW,
DETACHED_PROCESS or setsid) because Ctrl+C has to end them too; detached, the run would wait for their
running tasks after Ctrl+C. No code a worker runs was found to write there (A-89).

The worker deaths of the G1 finding (WinError 6 at ``call_queue.get``) came from CPython's WMI query, see
``avoid_wmi``; NeuroGrid's processes call it before any library can ask ``platform``.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from multiprocessing import context as mp_context
from multiprocessing.process import BaseProcess
from typing import Any, TypeVar

STDIO = (0, 1, 2)
_P = TypeVar("_P")
_START_LOCK = threading.Lock()  # POSIX: one start at a time changes the descriptors 0-2 of this process
_CONTEXTS: dict[str, mp_context.BaseContext] = {}


def _no_wmi(*_keys: str) -> Any:
    raise OSError("not supported")


def avoid_wmi() -> None:
    """``platform`` in this process does not query WMI; it uses ``ver`` and the environment, as before
    CPython 3.12.

    CPython 3.12 asks WMI through ``_wmi.exec_query`` (``platform.uname``, e.g. at ``import scipy.signal``).
    That function waits 1000 ms for COM and 100 ms for the connection (gh-112278) and then returns with
    WAIT_TIMEOUT while its query thread keeps running with a pointer to the returned call's stack data
    (``PC/_wmimodule.cpp``: ``struct _query_data data`` is a local, the thread reads ``data->writePipe``
    and closes it at its end). The thread then closes whatever handle value it reads there: any handle of
    the process, for example the semaphore of a worker's call queue (WinError 6 at ``call_queue.get``,
    the G1 finding). On the computer of the G1 run every WMI query missed these waits (WinError 258 after
    about 0.3 s). CPython 3.13 copies the data into the thread; 3.12 receives security fixes only.
    """
    if sys.platform != "win32":
        return
    import platform

    if "_wmi_query" in platform.__dict__:
        platform.__dict__["_wmi_query"] = _no_wmi


def to_null_device() -> None:
    """Descriptors 0-2 and sys.stdin, sys.stdout and sys.stderr of this worker on the null device.

    Does nothing in a process without a multiprocessing parent (NeuroGrid's own process keeps its console).
    """
    if multiprocessing.parent_process() is None:
        return
    null = os.open(os.devnull, os.O_RDWR)
    try:
        for fd in STDIO:
            if fd != null:
                os.dup2(null, fd)
    finally:
        if null not in STDIO:
            os.close(null)
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()  # whatever is still buffered goes to the null device now
        except (OSError, ValueError):
            pass
    sys.stdin = open(0, encoding="utf-8", errors="replace", closefd=False)
    sys.stdout = open(1, "w", encoding="utf-8", errors="replace", closefd=False)
    sys.stderr = open(2, "w", encoding="utf-8", errors="replace", closefd=False)


def _flush_console() -> None:
    """This process's pending output goes to its console before a child is started."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()
        except (OSError, ValueError):
            pass


if sys.platform == "win32":
    import _winapi
    import msvcrt
    import subprocess
    from multiprocessing import popen_spawn_win32, reduction, spawn, util

    def _null_handle() -> int:
        """A new inheritable handle of the null device; the caller closes it."""
        fd = os.open(os.devnull, os.O_RDWR)
        try:
            current = _winapi.GetCurrentProcess()
            source = msvcrt.get_osfhandle(fd)
            return _winapi.DuplicateHandle(current, source, current, 0, True, _winapi.DUPLICATE_SAME_ACCESS)
        finally:
            os.close(fd)

    def _same_path(first: str, second: str) -> bool:
        return first == second or os.path.normcase(first) == os.path.normcase(second)

    def _close_handles(*handles: int) -> None:
        for handle in handles:
            _winapi.CloseHandle(handle)

    class NullStdioPopen(popen_spawn_win32.Popen):
        """``popen_spawn_win32.Popen`` (CPython 3.11 to 3.13) whose child gets the null device as its
        standard handles instead of copies of this process's console handles."""

        def __init__(self, process_obj: BaseProcess) -> None:
            """Replaces the constructor of the base class, which starts the child with the console."""
            prep_data = spawn.get_preparation_data(process_obj.name)
            # the child duplicates the read end itself (spawn_main); it stays open until the finalizer
            rhandle, whandle = _winapi.CreatePipe(None, 0)
            wfd = msvcrt.open_osfhandle(whandle, 0)
            cmd = spawn.get_command_line(parent_pid=os.getpid(), pipe_handle=rhandle)
            python_exe = spawn.get_executable()
            env: Any = None
            base = getattr(sys, "_base_executable", sys.executable)
            in_venv = getattr(popen_spawn_win32, "WINENV", not _same_path(sys.executable, base))
            if in_venv and _same_path(python_exe, sys.executable):
                # in a virtual environment the base interpreter starts directly (bpo-35797)
                cmd[0] = python_exe = base
                env = os.environ.copy()
                env["__PYVENV_LAUNCHER__"] = sys.executable
            command = " ".join(f'"{part}"' for part in cmd)
            null = _null_handle()
            startup = subprocess.STARTUPINFO(
                # CPython 3.13 passes STARTF_FORCEOFFFEEDBACK too (no busy cursor while the worker starts)
                dwFlags=subprocess.STARTF_USESTDHANDLES | getattr(subprocess, "STARTF_FORCEOFFFEEDBACK", 0),
                hStdInput=null,
                hStdOutput=null,
                hStdError=null,
                lpAttributeList={"handle_list": [null]},
            )
            with os.fdopen(wfd, "wb", closefd=True) as to_child:
                try:
                    try:
                        hp, ht, pid, _tid = _winapi.CreateProcess(
                            python_exe, command, None, None, True, 0, env, None, startup
                        )
                    finally:
                        _winapi.CloseHandle(null)
                    _winapi.CloseHandle(ht)
                except BaseException:
                    _winapi.CloseHandle(rhandle)
                    raise
                self.pid = pid
                self.returncode = None
                self._handle = hp
                self.sentinel = int(hp)
                self.finalizer = util.Finalize(self, _close_handles, (self.sentinel, int(rhandle)))
                mp_context.set_spawning_popen(self)
                try:
                    reduction.dump(prep_data, to_child)
                    reduction.dump(process_obj, to_child)
                finally:
                    mp_context.set_spawning_popen(None)

    class QuietSpawnProcess(mp_context.SpawnProcess):
        @staticmethod
        def _Popen(process_obj: BaseProcess) -> popen_spawn_win32.Popen:
            return NullStdioPopen(process_obj)

    class QuietSpawnContext(mp_context.SpawnContext):
        Process = QuietSpawnProcess

    _QUIET: dict[str, type[mp_context.BaseContext]] = {"spawn": QuietSpawnContext}

else:
    import fcntl
    from multiprocessing import popen_fork, popen_spawn_posix

    def _new_start_lock() -> None:
        """A forked child gets the lock in the state of the forking thread: a fresh one."""
        global _START_LOCK
        _START_LOCK = threading.Lock()

    os.register_at_fork(after_in_child=_new_start_lock)

    @contextmanager
    def null_descriptors() -> Iterator[None]:
        """Descriptors 0-2 of this process on the null device while a child process is started (it
        inherits them); restored afterwards, a descriptor that was closed is closed again."""
        _flush_console()
        with _START_LOCK:
            saved: dict[int, int | None] = {}
            for fd in STDIO:
                try:  # the copies lie above 0-2 even if one of them is closed
                    saved[fd] = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 3)
                except OSError:
                    saved[fd] = None
            null = os.open(os.devnull, os.O_RDWR)  # takes a closed one of 0-2 if there is one
            try:
                for fd in STDIO:
                    if fd != null:
                        os.dup2(null, fd)
                yield
            finally:
                if null not in STDIO:
                    os.close(null)
                for fd, copy in saved.items():
                    if copy is None:
                        os.close(fd)
                    else:
                        os.dup2(copy, fd)
                        os.close(copy)

    class NullStdioForkPopen(popen_fork.Popen):
        def __init__(self, process_obj: BaseProcess) -> None:
            with null_descriptors():
                super().__init__(process_obj)

    class NullStdioSpawnPopen(popen_spawn_posix.Popen):
        def __init__(self, process_obj: BaseProcess) -> None:
            with null_descriptors():
                super().__init__(process_obj)

    class QuietForkProcess(mp_context.ForkProcess):
        @staticmethod
        def _Popen(process_obj: BaseProcess) -> popen_fork.Popen:
            return NullStdioForkPopen(process_obj)

    class QuietSpawnProcess(mp_context.SpawnProcess):
        @staticmethod
        def _Popen(process_obj: BaseProcess) -> popen_spawn_posix.Popen:
            return NullStdioSpawnPopen(process_obj)

    class QuietForkContext(mp_context.ForkContext):
        Process = QuietForkProcess

    class QuietSpawnContext(mp_context.SpawnContext):
        Process = QuietSpawnProcess

    _QUIET: dict[str, type[mp_context.BaseContext]] = {"fork": QuietForkContext, "spawn": QuietSpawnContext}

    try:  # the forkserver needs fd passing (reduction.HAVE_SEND_HANDLE)
        from multiprocessing import popen_forkserver
    except ImportError:  # pragma: no cover - every supported POSIX platform has it
        pass
    else:

        class NullStdioForkServerPopen(popen_forkserver.Popen):
            """The forkserver itself is started by the first such start, so it and all its children
            have the null device."""

            def __init__(self, process_obj: BaseProcess) -> None:
                with null_descriptors():
                    super().__init__(process_obj)

        class QuietForkServerProcess(mp_context.ForkServerProcess):
            @staticmethod
            def _Popen(process_obj: BaseProcess) -> popen_forkserver.Popen:
                return NullStdioForkServerPopen(process_obj)

        class QuietForkServerContext(mp_context.ForkServerContext):
            Process = QuietForkServerProcess

        _QUIET["forkserver"] = QuietForkServerContext

    def _quiet_resource_tracker(method: str) -> None:
        """spawn and forkserver: multiprocessing's resource tracker runs on the null device.

        With these methods a pool's semaphores are named (fork unlinks them at once) and registered with
        the tracker, which the first of them starts in ``ProcessPoolExecutor.__init__``, before any process
        of the pool and so outside ``null_descriptors``: the tracker inherits descriptors 0-2 and gets
        ``sys.stderr.fileno()``. If this process ends without its finalizers (SIGTERM, SIGKILL, the OOM
        killer), the tracker would print ``resource_tracker: There appear to be N leaked semaphore objects``
        with its install path. Started here, inside ``null_descriptors``, it writes to the null device; a
        running tracker is only probed, one that died is started again here."""
        if method == "fork":
            return
        from multiprocessing import resource_tracker

        with null_descriptors():
            resource_tracker.ensure_running()


def default_start_method() -> str:
    """The start method a pool would use: the one set for this process, otherwise the platform's default
    (the first of ``get_all_start_methods``)."""
    return multiprocessing.get_start_method(allow_none=True) or multiprocessing.get_all_start_methods()[0]


def pool_context(method: str | None = None) -> mp_context.BaseContext:
    """The multiprocessing context for NeuroGrid's process pools (``mp_context=``): ``method`` or the
    default start method, with processes that start on the null device. On POSIX with spawn or forkserver
    multiprocessing's resource tracker, which a new pool uses at once, is started on the null device too."""
    name = method or default_start_method()
    if name not in _CONTEXTS:
        if name not in _QUIET:
            raise ValueError(f"unsupported start method: {name}")
        _CONTEXTS[name] = _QUIET[name]()
    if sys.platform != "win32":
        _quiet_resource_tracker(name)
    return _CONTEXTS[name]


def quiet_pool(pool: _P) -> _P:
    """``pool`` (a ``ProcessPoolExecutor``) whose thread in this process that feeds its call queue prints
    nothing; anything else (a stand-in of the tests) is returned unchanged.

    That thread (multiprocessing's queue feeder) writes the pickled tasks into the pipe the workers read. A
    send that fails goes to ``_on_queue_feeder_error``, which concurrent.futures hands to
    ``traceback.print_exc()`` unless the object is a task that could not be pickled: a traceback with the
    install path of Python on NeuroGrid's console. That happens after a worker died: CPython closes the
    pipe (gh-107219, Windows) and 3.11 then still puts a stop signal into it for every worker that has not
    exited yet (``terminate_broken``, ``shutdown_workers``; 3.12 and later skip that for a broken pool), whose
    send fails with ``OSError: handle is closed``. The pool reports the death itself (BrokenProcessPool), so
    such a failure only goes to multiprocessing's debug log; a task that cannot be pickled still fails its
    own future."""
    from concurrent.futures import process as futures_process
    from multiprocessing import util

    call_queue = getattr(pool, "_call_queue", None)
    if not isinstance(call_queue, futures_process._SafeQueue):
        return pool
    # weak: the feeder thread must not keep the queue alive (collected, its finalizer stops the thread)
    report = weakref.WeakMethod(call_queue._on_queue_feeder_error)

    def on_feeder_error(error: Exception, obj: object) -> None:
        method = report()
        if isinstance(obj, futures_process._CallItem) and method is not None:
            method(error, obj)  # its future gets the error, as in CPython
        else:  # pickled bytes or a stop signal: the pipe was closed after a worker died
            util.debug("queue feeder of a pool: send failed: %r", error)

    call_queue.__dict__["_on_queue_feeder_error"] = on_feeder_error  # the feeder thread takes it at its start
    return pool


__all__ = ["STDIO", "avoid_wmi", "default_start_method", "pool_context", "quiet_pool", "to_null_device"]
