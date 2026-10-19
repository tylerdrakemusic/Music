"""Process-wide lock shared by tee approval and catalog mutations."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Iterator


TEE_IMAGE_APPROVAL_LOCK_PATH = (
    Path(tempfile.gettempdir()) / "heartmusic-tee-image-approval.lock"
)
TEE_IMAGE_APPROVAL_LOCK_TIMEOUT_SECONDS = 10.0
_THREAD_LOCK = threading.RLock()
_LOCK_STATE = threading.local()


@contextmanager
def tee_image_approval_lock(
    *,
    lock_path: Path | None = None,
    timeout_seconds: float | None = None,
) -> Iterator[None]:
    """Serialize supported tee-image mutations across threads and processes."""
    if timeout_seconds is None:
        timeout_seconds = TEE_IMAGE_APPROVAL_LOCK_TIMEOUT_SECONDS
    if timeout_seconds < 0:
        raise ValueError("lock timeout must be non-negative")

    resolved_lock_path = Path(lock_path or TEE_IMAGE_APPROVAL_LOCK_PATH).absolute()
    lock_key = (
        str(resolved_lock_path).casefold()
        if os.name == "nt"
        else str(resolved_lock_path)
    )
    deadline = time.monotonic() + timeout_seconds
    if not _THREAD_LOCK.acquire(timeout=timeout_seconds):
        raise TimeoutError("tee approval is busy; retry after the active operation")

    lock_file = None
    owns_os_lock = False
    previous_depth = getattr(_LOCK_STATE, "depth", 0)
    try:
        if previous_depth:
            if getattr(_LOCK_STATE, "lock_key", None) != lock_key:
                raise RuntimeError("nested tee approval locks must use the same lock path")
            _LOCK_STATE.depth = previous_depth + 1
        else:
            resolved_lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = resolved_lock_path.open("a+b")
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()

            while True:
                try:
                    lock_file.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.lockf(
                            lock_file.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                            1,
                            0,
                        )
                    owns_os_lock = True
                    _LOCK_STATE.depth = 1
                    _LOCK_STATE.lock_key = lock_key
                    break
                except OSError as exc:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            "tee approval is busy; retry after the active operation"
                        ) from exc
                    threading.Event().wait(min(0.05, remaining))

        yield
    finally:
        try:
            if previous_depth:
                _LOCK_STATE.depth = previous_depth
            elif owns_os_lock and lock_file is not None:
                try:
                    lock_file.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.lockf(lock_file.fileno(), fcntl.LOCK_UN, 1, 0)
                finally:
                    _LOCK_STATE.depth = 0
                    _LOCK_STATE.lock_key = None
                    lock_file.close()
            elif lock_file is not None:
                lock_file.close()
        finally:
            _THREAD_LOCK.release()
