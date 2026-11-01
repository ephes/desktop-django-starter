"""Run a Django manage.py command as a child of a desktop shell.

The desktop shells (Electron, Tauri) start every backend process through this
small launcher instead of running manage.py directly:

    python desktop_process_guard.py --app-key KEY --instance ID --watch-stdin \
        -- manage.py runserver 127.0.0.1:PORT --noreload

It adds three things to the process and then runs manage.py in-process, so
the process ID the shell sees is the Django process itself:

- On Windows it puts itself into a Job Object with KILL_ON_JOB_CLOSE. Every
  process it starts joins the job, and when this process ends for any reason
  the job's last handle closes and Windows terminates the whole tree.
- With --watch-stdin it watches the pipe the shell holds open on its stdin.
  When the shell exits or crashes, the operating system closes that pipe, the
  read returns end-of-file, and this process exits instead of living on as an
  orphan.
- --app-key and --instance are not interpreted here. They stay visible in the
  command line, so the shell can find and stop leftovers from a previous
  crashed run of the same app (see shells/electron/scripts/orphan-processes.cjs).

Only the Python standard library is used, so it runs in the bundled runtime of
any wrapped Django project.
"""

from __future__ import annotations

import os
import runpy
import sys
import threading

KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

# Kept for the life of the process; closing it is what ends the job's tree.
_job_handle = None


def parse_arguments(argv: list[str]) -> tuple[dict[str, str | bool], list[str]]:
    if "--" not in argv:
        raise SystemExit("usage: desktop_process_guard.py [options] -- manage.py ARGS...")
    separator = argv.index("--")
    options: dict[str, str | bool] = {"watch_stdin": False}
    own, command = argv[:separator], argv[separator + 1 :]
    index = 0
    while index < len(own):
        name = own[index]
        if name == "--watch-stdin":
            options["watch_stdin"] = True
        elif name in {"--app-key", "--instance"} and index + 1 < len(own):
            options[name[2:].replace("-", "_")] = own[index + 1]
            index += 1
        else:
            raise SystemExit(f"desktop_process_guard.py: unknown option {name}")
        index += 1
    if not command:
        raise SystemExit("desktop_process_guard.py: missing manage.py command")
    return options, command


def job_object_structures():
    """Return the ctypes structure for JOBOBJECT_EXTENDED_LIMIT_INFORMATION."""
    import ctypes

    # Explicit 32-bit DWORD fields: ctypes.wintypes.DWORD is 64-bit off Windows.

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    return ExtendedLimitInformation


def join_kill_on_close_job() -> None:
    """Put this process (and everything it starts) into a kill-on-close job."""
    global _job_handle
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())

    information = job_object_structures()()
    information.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    _job_handle = job


def exit_when_stdin_closes(fd: int | None = None) -> threading.Thread:
    """Exit the process once the shell's end of the stdin pipe goes away."""
    source_fd = sys.stdin.fileno() if fd is None else fd

    def watch() -> None:
        # A raw os.read() holds no interpreter lock, unlike sys.stdin.buffer,
        # so normal interpreter shutdown is not blocked by this daemon thread.
        try:
            while os.read(source_fd, 65536):
                pass
        except OSError:
            pass
        # The shell is gone: skip interpreter cleanup that could block on
        # running threads, and let the OS (and the job object) take the rest.
        os._exit(0)

    thread = threading.Thread(target=watch, name="desktop-shell-watchdog", daemon=True)
    thread.start()
    return thread


def run_manage_command(command: list[str]) -> None:
    manage_path = os.path.abspath(command[0])
    sys.argv = [manage_path, *command[1:]]
    sys.path[0] = os.path.dirname(manage_path)
    runpy.run_path(manage_path, run_name="__main__")


def main(argv: list[str] | None = None) -> None:
    options, command = parse_arguments(sys.argv[1:] if argv is None else argv)
    if os.name == "nt":
        try:
            join_kill_on_close_job()
        except OSError as error:
            sys.stderr.write(f"desktop_process_guard: could not create job object: {error}\n")
    if options["watch_stdin"]:
        exit_when_stdin_closes()
    run_manage_command(command)


if __name__ == "__main__":
    main()
