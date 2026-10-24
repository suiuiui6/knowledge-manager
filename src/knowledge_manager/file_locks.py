from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from functools import wraps
from inspect import signature
from pathlib import Path
from typing import Iterator


_REGISTRY_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}
_LOCAL = threading.local()


@contextmanager
def kb_write_lock(kb_path: Path, *, timeout: float = 60.0) -> Iterator[None]:
    """Serialize cooperating writers on one host; kernel releases locks on exit.

    The persistent lock file must never be unlinked: all processes must lock the
    same inode. Nesting in the owning thread is supported. Network filesystems
    and writers that bypass this API are outside this contract.
    """
    key = str(kb_path.resolve())
    deadline = time.monotonic() + timeout
    with _REGISTRY_GUARD:
        local_lock = _LOCKS.setdefault(key, threading.RLock())
    if not local_lock.acquire(timeout=max(0.0, timeout)):
        raise TimeoutError(f"knowledge-base write lock timed out: {kb_path}")
    held = getattr(_LOCAL, "held", None)
    if held is None:
        held = _LOCAL.held = set()
    try:
        if key in held:
            yield
            return
        path = kb_path / ".locks" / "write.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"knowledge-base write lock timed out: {kb_path}") from exc
                    time.sleep(0.01)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        local_lock.release()


def serialized_write(function):
    """Protect the full read/modify/write operation, including nested writes."""
    sig = signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        kb = sig.bind(*args, **kwargs).arguments["kb_path"]
        with kb_write_lock(kb):
            return function(*args, **kwargs)

    return wrapped
