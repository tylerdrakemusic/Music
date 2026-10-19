r"""Generate tee artwork from approved concepts and retain exact-image approvals.
Run from the Music repository root with
``python -m src.merch.tee_image_approval --chat-start --catalog-id TJD-TEE-001``.
Use ``--count`` to authorize one through four independent candidate calls; the
default is two. Resolve each displayed image with ``--chat-decide`` and cancel
an unfinished session with ``--chat-cancel``.
"""
from __future__ import annotations


import argparse
from collections import Counter
import hashlib
import hmac
from io import BytesIO
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Protocol

from PIL import Image

from src.merch.tee_image_lock import tee_image_approval_lock as _tee_approval_lock
from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.utils import init_db
from tools.color_transparency import delta_e_ciede2000, rgb_to_lab


def _resolve_main_project_root(project_root: Path) -> Path:
    try:
        git_common_dir = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return project_root

    common_git_path = Path(git_common_dir)
    if common_git_path.name != ".git":
        return project_root
    return common_git_path.parent.resolve()


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_ROOT = (
    _resolve_main_project_root(_PROJECT_ROOT) / "output" / "images" / "tee-merch"
)
_PENDING_ROOT = Path(tempfile.gettempdir()) / "tee-image-approval-sessions"
_WORKSPACE_ROOT = Path(r"F:\⊕Workspace")
_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH = {
    "image_cascade.py": "6c8a9be85c8598198f933f410eb94e5d5fd38bf0dcbff6251c038b13af183687",
    "dalle3/__init__.py": "d99c26bc8bc668b95f2cbfb125a65524ea7f0bf07980f7b5fb9426b99396b071",
    "dalle3/client.py": "3f574df139799cc6b5b1f0a12b11472719f18dea9d4f024e20913d63089f2602",
    "huggingface/__init__.py": "2d6601370f7fa1eeb36304be7955a5ef9da74fc0a1a4358be898eb191ef80a3c",
    "huggingface/client.py": "e3ed8f772666eb53092739b4ff2ff575303f0764bf14cf1055e138dedf9ca82c",
    "pollinations/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "pollinations/client.py": "c571a193d04b6811c4b0fbeda8e43ecad82878b64d3ab9ed26e62d908ff23b8a",
}
_WORKSPACE_CASCADE_RELATIVE_PATHS = frozenset(
    {
        "image_cascade.py",
        "dalle3/__init__.py",
        "dalle3/client.py",
        "huggingface/__init__.py",
        "huggingface/client.py",
        "pollinations/__init__.py",
        "pollinations/client.py",
    }
)
_TEE_INTEGRITY_KEY_DOMAIN = b"heartmusic.tee-image-approval.integrity-key.v1"
_ALLOWED_TEE_PROVIDER_TUPLES = frozenset(
    {("fal-ai", "black-forest-labs/FLUX.1-Krea-dev", "fal-ai/flux/krea")}
)
_PROMPT_REVISION = "tee-artwork-prompt-v3"
_MAX_BATCH_SIZE = 4
_CANDIDATE_ART_DIRECTIONS = (
    "Vintage screen-print artwork: center the main subject in a "
    "balanced, emblematic composition with a sparse background.",
    "Abstract artwork: use a wide environmental composition, placing the "
    "main subject off-center and giving the setting more space.",
    "Line-work artwork: use an intimate close crop on the concept's key "
    "subjects, reducing secondary setting details.",
    "Woodcut-inspired artwork: use a dynamic diagonal composition with "
    "the main subject crossing the frame and bold, simplified background shapes.",
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_DIRECTORY_MTIME_SENTINEL_NS = 4_000_000_000_000_000_000


def _matches_image_signature(suffix: str, content: bytes) -> bool:
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def _is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(path_stat.st_mode) or bool(
        getattr(path_stat, "st_file_attributes", 0) & 0x400
    )


def _stat_fingerprint(path_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        path_stat.st_dev,
        path_stat.st_ino,
        path_stat.st_size,
        path_stat.st_mtime_ns,
        path_stat.st_ctime_ns,
    )


def _pin_directory_mtime_for_mutation_detection(path: Path) -> None:
    directory_stat = path.stat()
    # Future mtime makes directory-entry changes visible on coarse-resolution filesystems.
    os.utime(
        path,
        ns=(
            directory_stat.st_atime_ns,
            max(directory_stat.st_mtime_ns, _DIRECTORY_MTIME_SENTINEL_NS),
        ),
    )
def _write_json_exclusive(path: Path, data: object) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    _write_file_exclusive_without_reparse_components(path, payload)


def _live_connection() -> sqlite3.Connection:
    init_db.use_worktree_aware_db_path(_PROJECT_ROOT)
    return init_db.get_connection()


class ImageCascade(Protocol):
    def generate(self, prompt: str, *, output_dir: Path) -> object: ...


@dataclass(frozen=True)
class TeeImageCandidate:
    """One generated candidate shown to the operator for an exact-image decision."""

    candidate_id: str
    path: Path
    provider: str
    model: str
    exact_prompt: str
    provider_route: str | None = None


@dataclass(frozen=True)
class TeeImageBatchResult:
    """Summary of a batch without retaining rejected image files or decisions."""

    run_id: str
    approved: tuple[TeeImageCandidate, ...]
    rejected_count: int
    failures: tuple[dict[str, object], ...]


Decision = Callable[[TeeImageCandidate], bool]


def _resolve_workspace_src() -> Path:
    return _WORKSPACE_ROOT / "src"


def _workspace_path_has_reparse_point(path: Path) -> bool:
    current = Path(os.path.abspath(path))
    while True:
        if _is_reparse_point(current):
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _workspace_cascade_source_path_is_safe(
    workspace_src: Path,
    integration_dir: Path,
    source_path: Path,
) -> bool:
    try:
        resolved_src = workspace_src.resolve(strict=True)
        resolved_integration = integration_dir.resolve(strict=True)
        resolved_source = source_path.resolve(strict=True)
        return (
            not _workspace_path_has_reparse_point(workspace_src)
            and not _workspace_path_has_reparse_point(source_path)
            and resolved_integration.is_relative_to(resolved_src)
            and resolved_source.is_relative_to(resolved_integration)
            and resolved_source == source_path.absolute()
            and resolved_integration.is_dir()
            and stat.S_ISREG(source_path.lstat().st_mode)
        )
    except (OSError, RuntimeError):
        return False


def _read_file_without_reparse_components(
    source_path: Path,
    *,
    expected_fingerprint: tuple[int, int, int, int, int] | list[int] | None = None,
) -> bytes:
    absolute_path = Path(os.path.abspath(source_path))
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        get_file_type = kernel32.GetFileType
        get_file_type.argtypes = (wintypes.HANDLE,)
        get_file_type.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        class FileBasicInfo(ctypes.Structure):
            _fields_ = (
                ("creation_time", ctypes.c_longlong),
                ("last_access_time", ctypes.c_longlong),
                ("last_write_time", ctypes.c_longlong),
                ("change_time", ctypes.c_longlong),
                ("attributes", wintypes.DWORD),
            )

        get_file_information = kernel32.GetFileInformationByHandleEx
        get_file_information.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        get_file_information.restype = wintypes.BOOL

        file_share_read = 0x00000001
        open_existing = 3
        file_flag_open_reparse_point = 0x00200000
        file_flag_backup_semantics = 0x02000000
        file_attribute_directory = 0x00000010
        file_attribute_reparse_point = 0x00000400
        file_basic_info = 0
        invalid_handle = ctypes.c_void_p(-1).value

        def open_checked(path: Path, *, directory: bool) -> int:
            desired_access = 0x00000080 if directory else 0x80000080
            flags = file_flag_open_reparse_point
            if directory:
                flags |= file_flag_backup_semantics
            handle = create_file(
                str(path),
                desired_access,
                file_share_read,
                None,
                open_existing,
                flags,
                None,
            )
            if handle == invalid_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            info = FileBasicInfo()
            if not get_file_information(
                handle,
                file_basic_info,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                error = ctypes.WinError(ctypes.get_last_error())
                close_handle(handle)
                raise error
            is_directory = bool(info.attributes & file_attribute_directory)
            if (
                info.attributes & file_attribute_reparse_point
                or is_directory != directory
                or (not directory and get_file_type(handle) != 1)
            ):
                close_handle(handle)
                raise RuntimeError("Workspace image cascade failed path validation")
            return int(handle)

        directory_handles: list[int] = []
        file_handle: int | None = None
        try:
            if not absolute_path.anchor:
                raise RuntimeError("Workspace image cascade failed path validation")
            current = Path(absolute_path.anchor)
            directory_handles.append(open_checked(current, directory=True))
            for component in absolute_path.parts[1:-1]:
                current = current / component
                directory_handles.append(open_checked(current, directory=True))
            file_handle = open_checked(current / absolute_path.name, directory=False)
            descriptor = msvcrt.open_osfhandle(
                file_handle, os.O_RDONLY | os.O_BINARY
            )
            file_handle = None
            with os.fdopen(descriptor, "rb") as source_file:
                opened_fingerprint = _stat_fingerprint(os.fstat(source_file.fileno()))
                if expected_fingerprint is not None and tuple(
                    expected_fingerprint
                ) != opened_fingerprint:
                    raise RuntimeError("file changed before it could be read")
                return source_file.read()
        finally:
            if file_handle is not None:
                close_handle(file_handle)
            for handle in reversed(directory_handles):
                close_handle(handle)

    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory_flag or not absolute_path.anchor:
        raise RuntimeError("Workspace image cascade failed path validation")

    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    directory_fds: list[int] = []
    file_fd: int | None = None
    try:
        directory_fds.append(os.open(absolute_path.anchor, flags | directory_flag))
        for component in absolute_path.parts[1:-1]:
            directory_fds.append(
                os.open(component, flags | directory_flag, dir_fd=directory_fds[-1])
            )
        file_fd = os.open(absolute_path.name, flags, dir_fd=directory_fds[-1])
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise RuntimeError("Workspace image cascade failed path validation")
        opened_fingerprint = _stat_fingerprint(os.fstat(file_fd))
        if expected_fingerprint is not None and tuple(
            expected_fingerprint
        ) != opened_fingerprint:
            raise RuntimeError("file changed before it could be read")
        with os.fdopen(file_fd, "rb") as source_file:
            file_fd = None
            return source_file.read()
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for descriptor in reversed(directory_fds):
            os.close(descriptor)


def _write_file_exclusive_without_reparse_components(
    path: Path, content: bytes
) -> None:
    with _tee_approval_lock():
        _write_file_exclusive_unlocked(path, content)


def _write_file_exclusive_unlocked(
    path: Path, content: bytes
) -> None:
    absolute_path = Path(os.path.abspath(path))
    if not absolute_path.anchor or not absolute_path.name:
        raise RuntimeError("output path failed validation")
    created_output = False

    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        create_directory = kernel32.CreateDirectoryW
        create_directory.argtypes = (wintypes.LPCWSTR, wintypes.LPVOID)
        create_directory.restype = wintypes.BOOL
        get_file_type = kernel32.GetFileType
        get_file_type.argtypes = (wintypes.HANDLE,)
        get_file_type.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        class FileBasicInfo(ctypes.Structure):
            _fields_ = (
                ("creation_time", ctypes.c_longlong),
                ("last_access_time", ctypes.c_longlong),
                ("last_write_time", ctypes.c_longlong),
                ("change_time", ctypes.c_longlong),
                ("attributes", wintypes.DWORD),
            )

        get_file_information = kernel32.GetFileInformationByHandleEx
        get_file_information.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        get_file_information.restype = wintypes.BOOL

        file_attribute_directory = 0x10
        file_attribute_reparse_point = 0x400
        file_attribute_normal = 0x80
        file_flag_open_reparse_point = 0x00200000
        file_flag_backup_semantics = 0x02000000
        file_basic_info = 0
        file_share_read_write = 0x3
        file_share_read = 0x1
        open_existing = 3
        create_new = 1
        invalid_handle = ctypes.c_void_p(-1).value
        directory_handles: list[int] = []
        file_handle: int | None = None

        def open_directory(directory_path: Path) -> int:
            handle = create_file(
                str(directory_path),
                0x80,
                file_share_read_write,
                None,
                open_existing,
                file_flag_open_reparse_point | file_flag_backup_semantics,
                None,
            )
            if handle == invalid_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            info = FileBasicInfo()
            if not get_file_information(
                handle,
                file_basic_info,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                error = ctypes.WinError(ctypes.get_last_error())
                close_handle(handle)
                raise error
            if not info.attributes & file_attribute_directory or (
                info.attributes & file_attribute_reparse_point
            ):
                close_handle(handle)
                raise RuntimeError("output path contains a reparse point")
            return int(handle)

        try:
            current = Path(absolute_path.anchor)
            directory_handles.append(open_directory(current))
            for component in absolute_path.parts[1:-1]:
                current = current / component
                try:
                    directory_handle = open_directory(current)
                except OSError as exc:
                    if getattr(exc, "winerror", None) not in {2, 3}:
                        raise
                    if not create_directory(str(current), None):
                        create_error = ctypes.get_last_error()
                        if create_error not in {80, 183}:
                            raise ctypes.WinError(create_error)
                    directory_handle = open_directory(current)
                directory_handles.append(directory_handle)

            file_handle = create_file(
                str(absolute_path),
                0x40000000,
                file_share_read,
                None,
                create_new,
                file_flag_open_reparse_point | file_attribute_normal,
                None,
            )
            if file_handle == invalid_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            created_output = True
            info = FileBasicInfo()
            if not get_file_information(
                file_handle,
                file_basic_info,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if (
                info.attributes & file_attribute_reparse_point
                or info.attributes & file_attribute_directory
                or get_file_type(file_handle) != 1
            ):
                raise RuntimeError("output file failed handle validation")
            descriptor = msvcrt.open_osfhandle(
                file_handle, os.O_WRONLY | os.O_BINARY
            )
            file_handle = None
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(content)
                output_file.flush()
                os.fsync(output_file.fileno())
            created_output = False
        finally:
            if file_handle is not None:
                close_handle(file_handle)
            for handle in reversed(directory_handles):
                close_handle(handle)
            if created_output:
                try:
                    absolute_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return

    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory_flag:
        raise RuntimeError("secure output creation is unavailable on this platform")
    directory_flags = os.O_RDONLY | directory_flag | no_follow | getattr(os, "O_CLOEXEC", 0)
    directory_fds: list[int] = []
    file_fd: int | None = None
    try:
        directory_fds.append(os.open(absolute_path.anchor, directory_flags))
        for component in absolute_path.parts[1:-1]:
            try:
                directory_fd = os.open(
                    component, directory_flags, dir_fd=directory_fds[-1]
                )
            except FileNotFoundError:
                os.mkdir(component, dir_fd=directory_fds[-1])
                directory_fd = os.open(
                    component, directory_flags, dir_fd=directory_fds[-1]
                )
            directory_fds.append(directory_fd)
        file_fd = os.open(
            absolute_path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | no_follow
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_fds[-1],
        )
        created_output = True
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise RuntimeError("output file failed handle validation")
        with os.fdopen(file_fd, "wb") as output_file:
            file_fd = None
            output_file.write(content)
            output_file.flush()
            os.fsync(output_file.fileno())
        created_output = False
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for descriptor in reversed(directory_fds):
            os.close(descriptor)
        if created_output:
            try:
                absolute_path.unlink(missing_ok=True)
            except OSError:
                pass


def _read_workspace_cascade_source(
    workspace_src: Path,
    integration_dir: Path,
    relative_path: str,
) -> tuple[Path, bytes]:
    source_path = integration_dir / relative_path
    if not _workspace_cascade_source_path_is_safe(
        workspace_src, integration_dir, source_path
    ):
        raise RuntimeError("Workspace image cascade failed path validation")
    try:
        source_bytes = _read_file_without_reparse_components(source_path)
    except OSError as exc:
        raise RuntimeError("trusted Workspace image cascade is unavailable") from exc
    if not _workspace_cascade_source_path_is_safe(
        workspace_src, integration_dir, source_path
    ):
        raise RuntimeError("Workspace image cascade failed path validation")
    return source_path, source_bytes


def _workspace_cascade() -> ImageCascade:
    approved_hashes = _APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH
    if (
        not isinstance(approved_hashes, dict)
        or set(approved_hashes) != _WORKSPACE_CASCADE_RELATIVE_PATHS
        or any(
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in approved_hashes.values()
        )
    ):
        raise RuntimeError("Workspace image cascade failed provenance validation")

    workspace_src = _resolve_workspace_src()
    integration_dir = workspace_src / "integrations"
    source_paths: dict[str, Path] = {}
    verified_sources: dict[str, bytes] = {}

    for relative_path, expected_sha256 in approved_hashes.items():
        source_path, source_bytes = _read_workspace_cascade_source(
            workspace_src, integration_dir, relative_path
        )
        if hashlib.sha256(source_bytes).hexdigest() != expected_sha256:
            raise RuntimeError("Workspace image cascade failed provenance validation")
        source_paths[relative_path] = source_path
        verified_sources[relative_path] = source_bytes

    module_root = "_music_workspace_image_cascade_" + uuid.uuid4().hex
    modules: dict[str, ModuleType] = {}
    source_module_names: dict[str, str] = {}

    for relative_path, source_path in source_paths.items():
        relative = Path(relative_path)
        if relative_path == "image_cascade.py":
            module_name = module_root
            is_package = True
            package_path = integration_dir
        elif relative.name == "__init__.py":
            package_parts = relative.parts[:-1]
            module_name = f"{module_root}.{'.'.join(package_parts)}"
            is_package = True
            package_path = source_path.parent
        else:
            module_parts = (*relative.parts[:-1], relative.stem)
            module_name = f"{module_root}.{'.'.join(module_parts)}"
            is_package = False
            package_path = None

        module = ModuleType(module_name)
        module.__file__ = str(source_path)
        module.__package__ = module_name if is_package else module_name.rpartition(".")[0]
        if package_path is not None:
            module.__path__ = []
        sys.modules[module_name] = module
        modules[module_name] = module
        source_module_names[relative_path] = module_name

    for module_name, module in modules.items():
        if module_name == module_root:
            continue
        parent_name, child_name = module_name.rsplit(".", 1)
        setattr(modules[parent_name], child_name, module)

    execution_order = (
        "dalle3/client.py",
        "dalle3/__init__.py",
        "huggingface/client.py",
        "huggingface/__init__.py",
        "pollinations/client.py",
        "pollinations/__init__.py",
        "image_cascade.py",
    )

    class ClosedCascadeImportFinder:
        def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
            if fullname.startswith(module_root + ".") and fullname not in modules:
                raise ModuleNotFoundError(
                    f"unverified Workspace cascade module: {fullname}"
                )
            return None

    import_finder = ClosedCascadeImportFinder()
    quantum_module_name = "src.utils.quantum_rt"
    missing_quantum_module = object()
    previous_quantum_module = sys.modules.pop(
        quantum_module_name, missing_quantum_module
    )
    sys.modules[quantum_module_name] = None
    original_sys_path = list(sys.path)
    sys.meta_path.insert(0, import_finder)
    try:
        for relative_path in execution_order:
            module = modules[source_module_names[relative_path]]
            exec(
                compile(
                    verified_sources[relative_path],
                    str(source_paths[relative_path]),
                    "exec",
                ),
                module.__dict__,
            )
        factory = getattr(modules[module_root], "tee_image_cascade", None)
        if not callable(factory):
            raise RuntimeError("trusted Workspace source has no tee cascade factory")
        return factory()
    except Exception:
        for module_name, module in modules.items():
            if sys.modules.get(module_name) is module:
                sys.modules.pop(module_name, None)
        raise
    finally:
        if import_finder in sys.meta_path:
            sys.meta_path.remove(import_finder)
        sys.path[:] = original_sys_path
        if previous_quantum_module is missing_quantum_module:
            sys.modules.pop(quantum_module_name, None)
        else:
            sys.modules[quantum_module_name] = previous_quantum_module


def _validated_provider_tuple(result: object) -> tuple[str, str, str]:
    provider = getattr(result, "provider", None)
    model = getattr(result, "model", None)
    route = getattr(result, "route", None)
    if (
        type(provider) is not str
        or type(model) is not str
        or type(route) is not str
        or (provider, model, route) not in _ALLOWED_TEE_PROVIDER_TUPLES
    ):
        raise ValueError("image provider provenance is not authorized")
    return provider, model, route


def _derive_tee_integrity_key() -> bytes:
    database_key = os.environ.get("HEARTMUSIC_DB_KEY")
    if not isinstance(database_key, str) or not database_key.strip():
        raise RuntimeError("HEARTMUSIC_DB_KEY is required for tee approval integrity")
    try:
        key_bytes = database_key.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RuntimeError("HEARTMUSIC_DB_KEY is invalid for tee approval integrity") from exc
    if len(key_bytes) < 32:
        raise RuntimeError("HEARTMUSIC_DB_KEY is too short for tee approval integrity")
    return hmac.new(key_bytes, _TEE_INTEGRITY_KEY_DOMAIN, hashlib.sha256).digest()


def _presentation_hmac(
    state: dict[str, object],
    presentation_record: dict[str, object],
    image_digest: str,
) -> str:
    signed_record = {
        key: value
        for key, value in presentation_record.items()
        if key != "integrity_hmac_sha256"
    }
    payload = json.dumps(
        {
            "domain": "heartmusic.tee-image-approval.pending.v1",
            "session": state,
            "image_sha256": image_digest,
            "presentation": signed_record,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        _derive_tee_integrity_key(), payload, hashlib.sha256
    ).hexdigest()


def _approved_sidecar_hmac(sidecar: dict[str, object], image_digest: str) -> str:
    signed_sidecar = {
        key: value for key, value in sidecar.items() if key != "integrity_hmac_sha256"
    }
    payload = json.dumps(
        {
            "domain": "heartmusic.tee-image-approval.approved-sidecar.v1",
            "sidecar": signed_sidecar,
            "image_sha256": image_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        _derive_tee_integrity_key(), payload, hashlib.sha256
    ).hexdigest()


def _diagnostic_dict(diagnostic: object) -> dict[str, object]:
    if isinstance(diagnostic, dict):
        return {str(key): value for key, value in diagnostic.items()}
    if hasattr(diagnostic, "__dict__"):
        return {str(key): value for key, value in vars(diagnostic).items()}
    return {"error": str(diagnostic)}


def _provider_metadata_record(
    result: object,
) -> tuple[dict[str, object], dict[str, str]]:
    exposed = getattr(result, "provider_metadata", {})
    if not isinstance(exposed, dict):
        exposed = {}
    allowed_fields = {
        "job_id",
        "immutable_revision",
        "seed",
        "settings",
        "request_id",
    }
    metadata = {
        str(key): value for key, value in exposed.items() if key in allowed_fields
    }
    status = {
        field: "reported" if metadata.get(field) is not None else "unverified"
        for field in ("job_id", "immutable_revision", "seed", "settings")
    }
    return metadata, status


def _write_json(path: Path, data: dict[str, object]) -> None:
    with _tee_approval_lock():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)


def _find_entry(catalog: dict[str, object], catalog_id: str) -> dict[str, object]:
    entries = catalog["prompts"]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == catalog_id:
            return entry
    raise KeyError(f"tee concept not found: {catalog_id}")


def _has_approved_images(
    output_root: Path,
    catalog_id: str,
    image_prompt_revision: int,
    concept_revision: int,
    exact_prompt: str,
    *,
    allow_legacy_sidecars: bool,
) -> bool:
    catalog_dir = output_root / catalog_id
    if catalog_dir.is_symlink() or not catalog_dir.is_dir():
        return False

    resolved_catalog_dir = catalog_dir.resolve()
    for run_dir in catalog_dir.iterdir():
        if (
            run_dir.is_symlink()
            or not run_dir.is_dir()
            or not re.fullmatch(r"[0-9a-f]{32}", run_dir.name)
            or run_dir.resolve().parent != resolved_catalog_dir
        ):
            continue
        for sidecar_path in run_dir.glob("*.json"):
            match = re.fullmatch(r"([0-9a-f]{8})-([0-9]{2})\.json", sidecar_path.name)
            if (
                match is None
                or sidecar_path.is_symlink()
                or sidecar_path.resolve().parent != run_dir.resolve()
                or match.group(1) != run_dir.name[:8]
            ):
                continue
            candidate_number = int(match.group(2))
            if not 1 <= candidate_number <= _MAX_BATCH_SIZE:
                continue
            try:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(sidecar, dict):
                continue
            is_legacy_sidecar = (
                allow_legacy_sidecars
                and "image_prompt_revision" not in sidecar
                and isinstance(sidecar.get("catalog_revision"), str)
                and sidecar.get("concept_revision") == concept_revision
            )
            if any(
                (
                    sidecar.get("candidate_id") != sidecar_path.stem,
                    sidecar.get("catalog_id") != catalog_id,
                    sidecar.get("approval") != "approved",
                    sidecar.get("image_prompt_revision") != image_prompt_revision
                    and not is_legacy_sidecar,
                    sidecar.get("prompt_revision") != _PROMPT_REVISION,
                )
            ):
                continue
            if sidecar.get("concept_revision") != concept_revision:
                continue
            expected_prompt = _compose_candidate_prompt(exact_prompt, candidate_number)
            if sidecar.get("exact_prompt") != expected_prompt and not (
                is_legacy_sidecar
                and _legacy_prompt_matches(sidecar.get("exact_prompt"), expected_prompt)
            ):
                continue
            image_paths = [
                run_dir / f"{sidecar_path.stem}{suffix}"
                for suffix in _IMAGE_SUFFIXES
                if (run_dir / f"{sidecar_path.stem}{suffix}").is_file()
            ]
            if len(image_paths) != 1 or image_paths[0].is_symlink():
                continue
            image_path = image_paths[0]
            if image_path.resolve().parent != run_dir.resolve():
                continue
            image_digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            if sidecar.get("content_sha256") != image_digest:
                continue
            signature = sidecar.get("integrity_hmac_sha256")
            if (
                type(signature) is not str
                or not hmac.compare_digest(
                    signature, _approved_sidecar_hmac(sidecar, image_digest)
                )
            ):
                continue
            return True
    return False


def _compose_prompt(entry: dict[str, object], image_prompt_revision: int) -> str:
    palette = entry.get("palette", [])
    palette_text = ", ".join(str(color) for color in palette) if isinstance(palette, list) else str(palette)
    return "\n".join(
        (
            f"Catalog ID: {entry['id']}",
            f"Image prompt revision: {image_prompt_revision}",
            f"Prompt revision: {_PROMPT_REVISION}",
            f"Title: {entry['title']}",
            f"Concept: {entry['concept']}",
            f"Palette: {palette_text}",
            f"Print notes: {entry['print_notes']}",
            "Create the selected concept itself as standalone 2D design artwork. Do not depict clothing or apparel, wearers, garments, or garment/product mockups. Do not use clothing or apparel as the background. Require opaque artwork; do not use transparent rendering.",
        )
    )


def _compose_candidate_prompt(exact_prompt: str, candidate_number: int) -> str:
    direction = _CANDIDATE_ART_DIRECTIONS[candidate_number - 1]
    polarity = (
        "Use a dark blank and a lighter key edge."
        if candidate_number % 2 == 1
        else "Use a light blank and a darker key edge."
    )
    edge_constraints = (
        "Reserve the key shade for the border, and make it touch at least one "
        "point on the image perimeter. The frame may be irregular or partial "
        "and does not need to span every side."
    )
    return f"{direction}\n{polarity} {edge_constraints}\n{exact_prompt}"


def _hex_color(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def _sample_perimeter_key(source_path: Path) -> dict[str, object]:
    with Image.open(source_path) as image:
        if image.format != "PNG":
            raise ValueError("transparent derivatives require an approved PNG")
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        if width < 2 or height < 2:
            raise ValueError("PNG is too small to sample its perimeter")
        perimeter = (
            [(x, 0) for x in range(width)]
            + [(width - 1, y) for y in range(1, height)]
            + [(x, height - 1) for x in range(width - 2, -1, -1)]
            + [(0, y) for y in range(height - 2, 0, -1)]
        )
        if len(perimeter) < 64:
            raise ValueError("PNG perimeter has fewer than 64 distinct pixels")
        sample_positions = [
            round(index * len(perimeter) / 64) % len(perimeter)
            for index in range(64)
        ]
        sample_colors = [
            tuple(int(channel) for channel in rgb_image.getpixel(perimeter[position]))
            for position in sample_positions
        ]

    sample_labs = [rgb_to_lab(color) for color in sample_colors]
    clusters: list[list[int]] = []
    representatives: list[int] = []
    sample_cluster_ids: list[int] = []
    for sample_index, sample_lab in enumerate(sample_labs):
        cluster_id = next(
            (
                candidate_id
                for candidate_id, representative_index in enumerate(representatives)
                if delta_e_ciede2000(
                    sample_lab, sample_labs[representative_index]
                ) <= 10
            ),
            None,
        )
        if cluster_id is None:
            cluster_id = len(clusters)
            clusters.append([])
            representatives.append(sample_index)
        clusters[cluster_id].append(sample_index)
        sample_cluster_ids.append(cluster_id)

    cluster_order = sorted(range(len(clusters)), key=lambda item: len(clusters[item]), reverse=True)
    dominant_id = cluster_order[0]
    dominant_count = len(clusters[dominant_id])
    runner_up_count = len(clusters[cluster_order[1]]) if len(cluster_order) > 1 else 0
    dominant_samples = [cluster_id == dominant_id for cluster_id in sample_cluster_ids]
    if all(dominant_samples):
        longest_run = 64
    else:
        current_run = 0
        longest_run = 0
        for is_dominant in dominant_samples * 2:
            current_run = min(current_run + 1, 64) if is_dominant else 0
            longest_run = max(longest_run, current_run)

    selected_rgb = Counter(
        sample_colors[index] for index in clusters[dominant_id]
    ).most_common(1)[0][0]
    evidence: dict[str, object] = {
        "sample_count": 64,
        "sampled_colors": [_hex_color(color) for color in sample_colors],
        "clusters": [
            {
                "representative_color": _hex_color(sample_colors[representatives[index]]),
                "sample_count": len(clusters[index]),
            }
            for index in cluster_order
        ],
        "dominant_count": dominant_count,
        "runner_up_count": runner_up_count,
        "confidence_ratio": (
            round(dominant_count / runner_up_count, 3) if runner_up_count else None
        ),
        "longest_consecutive_dominant_run": longest_run,
        "delta_e00_cluster_threshold": 10,
        "minimum_consecutive_samples": 8,
        "minimum_dominant_multiple": 3,
    }
    if longest_run < 8 or dominant_count < 3 * runner_up_count:
        return {
            "selected_color": None,
            "evidence": evidence,
            "error": "perimeter key color did not meet the confidence rule",
        }
    return {
        "selected_color": _hex_color(selected_rgb),
        "evidence": evidence,
        "error": None,
    }


def _transparency_output_paths(source_path: Path) -> tuple[Path, Path]:
    for suffix_number in range(1, 1000):
        suffix = "" if suffix_number == 1 else f"_{suffix_number}"
        derivative_path = source_path.with_name(
            f"{source_path.stem}_transparent{suffix}.png"
        )
        sidecar_path = source_path.with_name(
            f"{source_path.stem}_transparency{suffix}.json"
        )
        if not any(
            path.exists() or _is_reparse_point(path)
            for path in (derivative_path, sidecar_path)
        ):
            return derivative_path, sidecar_path
    raise FileExistsError("no non-colliding transparent derivative name is available")


def _candidate_polarity(candidate_id: str) -> str:
    try:
        candidate_number = int(candidate_id.rsplit("-", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError("candidate ID does not contain an authorized number") from exc
    if not 1 <= candidate_number <= _MAX_BATCH_SIZE:
        raise ValueError("candidate ID is outside the authorized batch size")
    return (
        "lighter-key-on-dark-blank"
        if candidate_number % 2 == 1
        else "darker-key-on-light-blank"
    )


def _create_transparent_derivative(
    source_path: Path, candidate_id: str
) -> dict[str, object]:
    derivative_path: Path | None = None
    sidecar_path: Path | None = None
    derivative_published = False
    sidecar: dict[str, object] = {
        "candidate_id": candidate_id,
        "status": "failed",
        "selected_color": None,
        "polarity": None,
        "sampling": {},
        "settings": {
            "global_match": True,
            "tolerance": 10,
            "smooth_radius": 1,
        },
        "source_sha256": None,
        "output_sha256": None,
    }
    try:
        source_fingerprint = _stat_fingerprint(source_path.stat())
        source_bytes = _read_file_without_reparse_components(
            source_path, expected_fingerprint=source_fingerprint
        )
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        with _tee_approval_lock():
            derivative_path, sidecar_path = _transparency_output_paths(source_path)
        sidecar.update(
            {
                "source_path": str(source_path),
                "output_path": str(derivative_path),
                "sidecar_path": str(sidecar_path),
                "source_sha256": source_sha256,
                "polarity": _candidate_polarity(candidate_id),
            }
        )
        if source_path.suffix.lower() != ".png":
            raise ValueError("transparent derivatives require an approved PNG")

        with tempfile.TemporaryDirectory(prefix="tee-transparency-") as temporary_dir:
            temporary_root = Path(temporary_dir)
            temporary_source = temporary_root / "approved.png"
            temporary_derivative = temporary_root / "transparent.png"
            _write_file_exclusive_without_reparse_components(
                temporary_source, source_bytes
            )

            selection = _sample_perimeter_key(temporary_source)
            sidecar["sampling"] = selection["evidence"]
            selected_color = selection["selected_color"]
            if not isinstance(selected_color, str):
                raise ValueError(str(selection["error"]))
            sidecar["selected_color"] = selected_color

            subprocess.run(
                [
                    sys.executable,
                    str(_PROJECT_ROOT / "tools" / "color_transparency.py"),
                    str(temporary_source),
                    "--color",
                    selected_color,
                    "--global-match",
                    "--tolerance",
                    "10",
                    "--smooth-radius",
                    "1",
                    "--output",
                    str(temporary_derivative),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=_PROJECT_ROOT,
            )
            derivative_fingerprint = _stat_fingerprint(
                temporary_derivative.stat()
            )
            derivative_bytes = _read_file_without_reparse_components(
                temporary_derivative,
                expected_fingerprint=derivative_fingerprint,
            )
            with Image.open(BytesIO(derivative_bytes)) as derivative:
                if derivative.format != "PNG" or derivative.mode != "RGBA":
                    raise OSError("transparency CLI did not produce an RGBA PNG")

            current_source_bytes = _read_file_without_reparse_components(
                source_path, expected_fingerprint=source_fingerprint
            )
            if current_source_bytes != source_bytes:
                raise OSError("approved opaque source changed during conversion")

            with _tee_approval_lock():
                _write_file_exclusive_without_reparse_components(
                    derivative_path, derivative_bytes
                )
                derivative_published = True
                persisted_derivative = _read_file_without_reparse_components(
                    derivative_path
                )
                if persisted_derivative != derivative_bytes:
                    raise OSError("transparent derivative changed while being written")
                sidecar["output_sha256"] = hashlib.sha256(
                    persisted_derivative
                ).hexdigest()
                sidecar["status"] = "success"
                _write_json_exclusive(sidecar_path, sidecar)
        return sidecar
    except Exception as exc:
        error = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr or exc.stdout
            if detail:
                error = f"{error}: {str(detail).strip()}"
        sidecar["status"] = "failed"
        sidecar["error"] = error
        sidecar["output_sha256"] = None
        if derivative_published and derivative_path is not None:
            try:
                derivative_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                sidecar["cleanup_error"] = str(cleanup_error)
        if sidecar_path is not None:
            try:
                _write_json_exclusive(sidecar_path, sidecar)
            except Exception as sidecar_error:
                sidecar["sidecar_error"] = str(sidecar_error)
        return sidecar


def _legacy_prompt_matches(legacy_prompt: object, current_prompt: str) -> bool:
    if not isinstance(legacy_prompt, str):
        return False

    def without_revision(prompt: str) -> tuple[str, ...] | None:
        lines: list[str] = []
        revision_lines = 0
        for line in prompt.splitlines():
            if line.startswith("Catalog revision: ") or line.startswith(
                "Image prompt revision: "
            ):
                revision_lines += 1
                lines.append("<prompt revision>")
            else:
                lines.append(line)
        return tuple(lines) if revision_lines == 1 else None

    legacy_lines = without_revision(legacy_prompt)
    return legacy_lines is not None and legacy_lines == without_revision(current_prompt)


def _interactive_decision(candidate: TeeImageCandidate) -> bool:
    opener = getattr(os, "startfile", None)
    if opener is not None:
        opener(str(candidate.path))
    print(f"Candidate {candidate.candidate_id}: {candidate.path}")
    print(f"Provider: {candidate.provider}")
    print(f"Model: {candidate.model}")
    if candidate.provider_route is not None:
        print(f"Route: {candidate.provider_route}")
    while True:
        decision = input("Approve this exact image? [y/n]: ").strip().lower()
        if decision in {"y", "yes"}:
            return True
        if decision in {"n", "no"}:
            return False
        print("Enter y or n.")


class TeeImageApprovalFlow:
    """Run operator-authorized candidate batches and persist approved artwork only."""

    def __init__(
        self,
        catalog: TeePromptCatalog,
        output_root: Path = _OUTPUT_ROOT,
        *,
        cascade: ImageCascade | None = None,
        pending_root: Path | None = None,
    ) -> None:
        self.catalog = catalog
        self.output_root = Path(output_root).absolute()
        self.pending_root = Path(pending_root) if pending_root is not None else _PENDING_ROOT
        self.cascade = cascade if cascade is not None else _workspace_cascade()

    def _output_path(self, *parts: str) -> Path:
        root = self.output_root
        for ancestor in (root, *root.parents):
            if _is_reparse_point(ancestor):
                raise ValueError("output path may not contain symlinked or reparse-point parents")

        try:
            resolved_root = root.resolve(strict=False)
            candidate = root
            for part in parts:
                candidate = candidate / part
                if _is_reparse_point(candidate):
                    raise ValueError("output path may not contain symlinks or reparse points")
                if not candidate.resolve(strict=False).is_relative_to(resolved_root):
                    raise ValueError("output path escapes the configured output root")
        except OSError as exc:
            raise ValueError("output path could not be safely resolved") from exc
        return candidate

    def _prepare_generation(
        self, catalog_id: str
    ) -> tuple[dict[str, object], dict[str, object], int, int, str, str, bool]:
        self._output_path()
        if not re.fullmatch(r"TJD-TEE-\d{3}", catalog_id):
            raise ValueError("catalog ID must use the TJD-TEE-NNN format")

        with _tee_approval_lock():
            catalog = self.catalog.read_catalog()
            entry = _find_entry(catalog, catalog_id)
            if entry.get("concept_approval_status") != "concept_approved":
                raise ValueError("tee concept must be concept_approved before image generation")
            try:
                concept_revision = int(entry["concept_revision"])
                approval_revision = int(entry["concept_approval_revision"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "concept approval revision is missing; return the concept to curation"
                ) from exc

            if approval_revision != concept_revision:
                raise ValueError("concept revision changed; curation and explicit reapproval are required")

            image_prompt_revision = int(entry["image_prompt_revision"])
            catalog_version = str(entry["catalog_version"])
            approval_status = entry.get("exact_image_approval_status")
            exact_prompt = _compose_prompt(entry, image_prompt_revision)

        has_approved_images = _has_approved_images(
            self.output_root,
            catalog_id,
            image_prompt_revision,
            concept_revision,
            exact_prompt,
            allow_legacy_sidecars=(
                approval_status == "exact_image_approved"
            ),
        )
        with _tee_approval_lock():
            if not self._catalog_generation_is_current(
                catalog_id, concept_revision, image_prompt_revision
            ):
                raise ValueError(
                    "tee catalog changed while approved-image history was scanned; retry generation"
                )
            current_entry = self.catalog.read_prompt(catalog_id)
            if current_entry.get("exact_image_approval_status") != approval_status:
                raise ValueError(
                    "tee approved-image state changed while history was scanned; retry generation"
                )
            entry = self.catalog.reconcile_exact_image_approval(
                catalog_id,
                expected_image_prompt_revision=image_prompt_revision,
                expected_concept_revision=concept_revision,
                has_matching_approved_sidecar=has_approved_images,
            )
        entry["exact_image_approval_status"] = (
            "exact_image_approved" if has_approved_images else "exact_image_pending"
        )
        return (
            catalog,
            entry,
            concept_revision,
            image_prompt_revision,
            catalog_version,
            exact_prompt,
            has_approved_images,
        )

    def _catalog_generation_is_current(
        self,
        catalog_id: str,
        concept_revision: int,
        image_prompt_revision: int,
    ) -> bool:
        try:
            entry = self.catalog.read_prompt(catalog_id)
            current_revision = int(entry["concept_revision"])
            approval_revision = int(entry["concept_approval_revision"])
            current_prompt_revision = int(entry["image_prompt_revision"])
        except (KeyError, TypeError, ValueError):
            return False
        return (
            entry.get("concept_approval_status") == "concept_approved"
            and current_revision == concept_revision
            and approval_revision == current_revision
            and current_prompt_revision == image_prompt_revision
        )

    def _discard_stale_chat_generation_locked(
        self,
        session_dir: Path,
        state: dict[str, object],
        *,
        error: str = "concept or image prompt changed while the provider was generating",
        additional_failures: int = 0,
    ) -> dict[str, object] | None:
        if self._catalog_generation_is_current(
            str(state["catalog_id"]),
            int(state["concept_revision"]),
            int(state["image_prompt_revision"]),
        ):
            return None
        self._presentation_record_path(session_dir).unlink(missing_ok=True)
        shutil.rmtree(session_dir)
        failures = state.get("failures", [])
        return {
            "status": "stale_concept",
            "session_id": str(state["session_id"]),
            "run_id": str(state["run_id"]),
            "generated": int(state["generated_count"]),
            "approved": int(state["approved_count"]),
            "rejected": int(state["rejected_count"]),
            "failed": (len(failures) if isinstance(failures, list) else 0)
            + additional_failures,
            "error": error,
        }

    def _chat_session_directory(self, session_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("chat approval session ID is invalid")
        root = self.pending_root.resolve()
        session_dir = root / session_id
        if _is_reparse_point(session_dir) or session_dir.resolve().parent != root:
            raise ValueError("chat approval session path is invalid")
        return session_dir

    @staticmethod
    def _write_chat_session(session_dir: Path, state: dict[str, object]) -> None:
        _write_json(session_dir / "session.json", state)

    @staticmethod
    def _presentation_record_path(session_dir: Path) -> Path:
        return session_dir.parent / f".{session_dir.name}.presentation.json"

    def start_chat_batch(self, catalog_id: str, *, count: int = 2) -> dict[str, object]:
        if type(count) is not int or not 1 <= count <= _MAX_BATCH_SIZE:
            raise ValueError("candidate count must be between 1 and 4")
        _derive_tee_integrity_key()

        (
            catalog,
            _,
            concept_revision,
            image_prompt_revision,
            catalog_version,
            exact_prompt,
            _,
        ) = self._prepare_generation(catalog_id)
        run_id = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        session_dir = self._chat_session_directory(session_id)
        state: dict[str, object] = {
            "session_id": session_id,
            "catalog_id": catalog_id,
            "concept_revision": concept_revision,
            "image_prompt_revision": image_prompt_revision,
            "catalog_version": catalog_version,
            "prompt_revision": _PROMPT_REVISION,
            "exact_prompt": exact_prompt,
            "run_id": run_id,
            "total_count": count,
            "next_candidate_number": 1,
            "generated_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "failures": [],
            "transparency_failures": [],
            "pending_candidate": None,
        }
        with _tee_approval_lock():
            session_dir.mkdir(parents=True, exist_ok=False)
            self._write_chat_session(session_dir, state)
        return self._stage_next_chat_candidate(session_dir, state)

    def _persist_pending_chat_candidate(
        self,
        session_dir: Path,
        state: dict[str, object],
        *,
        candidate_id: str,
        candidate_number: int,
        candidate_prompt: str,
        provider: str,
        model: str,
        provider_route: str,
        result: object,
        suffix: str,
        staged_bytes: bytes,
    ) -> dict[str, object] | None:
        with _tee_approval_lock():
            session_id = str(state["session_id"])
            run_id = str(state["run_id"])
            try:
                current_session_dir, current_state = self._load_chat_session(
                    session_id
                )
            except ValueError:
                return None
            if (
                current_session_dir != session_dir
                or current_state.get("run_id") != run_id
                or current_state.get("pending_candidate") is not None
                or current_state.get("next_candidate_number") != candidate_number + 1
            ):
                return None
            state.clear()
            state.update(current_state)
            if not self._catalog_generation_is_current(
                str(state["catalog_id"]),
                int(state["concept_revision"]),
                int(state["image_prompt_revision"]),
            ):
                self._presentation_record_path(session_dir).unlink(missing_ok=True)
                shutil.rmtree(session_dir)
                return {
                    "status": "stale_concept",
                    "session_id": session_id,
                    "run_id": run_id,
                    "generated": int(state["generated_count"]),
                    "approved": int(state["approved_count"]),
                    "rejected": int(state["rejected_count"]),
                    "failed": len(state.get("failures", [])) + 1,
                    "error": "concept or image prompt changed while the provider was generating",
                }
            total_count = int(state["total_count"])
            staged_path = session_dir / f"{candidate_id}{suffix}"
            try:
                _write_file_exclusive_without_reparse_components(
                    staged_path, staged_bytes
                )
                persisted_bytes = _read_file_without_reparse_components(staged_path)
                if persisted_bytes != staged_bytes:
                    raise OSError("staged image changed while being written")
            except (OSError, RuntimeError, ValueError):
                staged_path.unlink(missing_ok=True)
                raise

            provider_metadata, provider_metadata_status = _provider_metadata_record(
                result
            )
            candidate_state = dict(state)
            candidate_state["generated_count"] = int(state["generated_count"]) + 1
            candidate_state["pending_candidate"] = {
                "candidate_id": candidate_id,
                "candidate_number": candidate_number,
                "image_name": staged_path.name,
                "provider": provider,
                "model": model,
                "provider_route": provider_route,
                "provider_metadata": provider_metadata,
                "provider_metadata_status": provider_metadata_status,
                "exact_prompt": candidate_prompt,
                "content_sha256": hashlib.sha256(staged_bytes).hexdigest(),
                "file_fingerprint": list(_stat_fingerprint(staged_path.stat())),
                "provider_diagnostics": [
                    _diagnostic_dict(item)
                    for item in getattr(result, "diagnostics", ())
                ],
            }
            presentation_path = self._presentation_record_path(session_dir)
            try:
                self._write_chat_session(session_dir, candidate_state)
                _pin_directory_mtime_for_mutation_detection(session_dir)
                presentation_record: dict[str, object] = {
                    "candidate_id": candidate_id,
                    "directory_fingerprint": list(
                        _stat_fingerprint(session_dir.stat())
                    ),
                }
                presentation_record["integrity_hmac_sha256"] = _presentation_hmac(
                    candidate_state,
                    presentation_record,
                    hashlib.sha256(staged_bytes).hexdigest(),
                )
                _write_json_exclusive(presentation_path, presentation_record)
            except (OSError, RuntimeError, TypeError, ValueError):
                presentation_path.unlink(missing_ok=True)
                staged_path.unlink(missing_ok=True)
                self._write_chat_session(session_dir, state)
                raise
            state.clear()
            state.update(candidate_state)
            return {
                "status": "candidate_pending",
                "session_id": session_id,
                "run_id": run_id,
                "candidate_id": candidate_id,
                "candidate_number": candidate_number,
                "count": total_count,
                "image_path": str(staged_path),
                "art_direction": candidate_prompt.splitlines()[0],
                "provider": provider,
                "model": model,
                "provider_route": provider_route,
                "provider_metadata": provider_metadata,
                "provider_metadata_status": provider_metadata_status,
            }

    def _stage_next_chat_candidate(
        self, session_dir: Path, state: dict[str, object]
    ) -> dict[str, object]:
        session_id = str(state["session_id"])
        catalog_id = str(state["catalog_id"])
        run_id = str(state["run_id"])
        total_count = int(state["total_count"])
        failures = state["failures"]
        assert isinstance(failures, list)

        while int(state["next_candidate_number"]) <= total_count:
            with _tee_approval_lock():
                if not session_dir.is_dir():
                    return {
                        "status": "cancelled",
                        "session_id": session_id,
                        "run_id": run_id,
                        "generated": int(state["generated_count"]),
                        "approved": int(state["approved_count"]),
                        "rejected": int(state["rejected_count"]),
                        "failed": len(failures),
                    }
                stale_result = self._discard_stale_chat_generation_locked(
                    session_dir,
                    state,
                    error="concept or image prompt changed before the next provider attempt",
                )
                if stale_result is not None:
                    return stale_result
                candidate_number = int(state["next_candidate_number"])
                state["next_candidate_number"] = candidate_number + 1
                self._write_chat_session(session_dir, state)
            candidate_id = f"{run_id[:8]}-{candidate_number:02d}"
            candidate_prompt = _compose_candidate_prompt(
                str(state["exact_prompt"]), candidate_number
            )
            with tempfile.TemporaryDirectory(prefix="tee-image-candidate-") as temporary_dir:
                temporary_root = Path(temporary_dir)
                try:
                    result = self.cascade.generate(candidate_prompt, output_dir=temporary_root)
                    provider, model, provider_route = _validated_provider_tuple(result)
                except Exception as exc:
                    with _tee_approval_lock():
                        if not session_dir.is_dir():
                            return {
                                "status": "cancelled",
                                "session_id": session_id,
                                "run_id": run_id,
                                "generated": int(state["generated_count"]),
                                "approved": int(state["approved_count"]),
                                "rejected": int(state["rejected_count"]),
                                "failed": len(failures),
                            }
                        stale_result = self._discard_stale_chat_generation_locked(
                            session_dir, state, additional_failures=1
                        )
                        if stale_result is not None:
                            return stale_result
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": str(exc),
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(exc, "diagnostics", ())
                                ],
                            }
                        )
                        self._write_chat_session(session_dir, state)
                    continue

                source_path = Path(result.path)
                suffix = source_path.suffix.lower()
                try:
                    source_fingerprint = _stat_fingerprint(source_path.stat())
                except OSError:
                    source_fingerprint = None
                if (
                    source_fingerprint is None
                    or
                    not source_path.is_file()
                    or _is_reparse_point(source_path)
                    or suffix not in _IMAGE_SUFFIXES
                    or not source_path.resolve().is_relative_to(temporary_root.resolve())
                ):
                    with _tee_approval_lock():
                        if not session_dir.is_dir():
                            return {
                                "status": "cancelled",
                                "session_id": session_id,
                                "run_id": run_id,
                                "generated": int(state["generated_count"]),
                                "approved": int(state["approved_count"]),
                                "rejected": int(state["rejected_count"]),
                                "failed": len(failures),
                            }
                        stale_result = self._discard_stale_chat_generation_locked(
                            session_dir, state, additional_failures=1
                        )
                        if stale_result is not None:
                            return stale_result
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": "image cascade returned a missing or unsupported image file",
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        self._write_chat_session(session_dir, state)
                    continue

                try:
                    staged_bytes = _read_file_without_reparse_components(
                        source_path, expected_fingerprint=source_fingerprint
                    )
                    if not _matches_image_signature(suffix, staged_bytes):
                        raise ValueError("image file content does not match its extension")
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    with _tee_approval_lock():
                        if not session_dir.is_dir():
                            return {
                                "status": "cancelled",
                                "session_id": session_id,
                                "run_id": run_id,
                                "generated": int(state["generated_count"]),
                                "approved": int(state["approved_count"]),
                                "rejected": int(state["rejected_count"]),
                                "failed": len(failures),
                            }
                        stale_result = self._discard_stale_chat_generation_locked(
                            session_dir, state, additional_failures=1
                        )
                        if stale_result is not None:
                            return stale_result
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": str(exc),
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        self._write_chat_session(session_dir, state)
                    continue
                try:
                    pending_response = self._persist_pending_chat_candidate(
                        session_dir,
                        state,
                        candidate_id=candidate_id,
                        candidate_number=candidate_number,
                        candidate_prompt=candidate_prompt,
                        provider=provider,
                        model=model,
                        provider_route=provider_route,
                        result=result,
                        suffix=suffix,
                        staged_bytes=staged_bytes,
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    recorded = self._record_chat_failure_if_active(
                        session_dir,
                        state,
                        {
                            "candidate_id": candidate_id,
                            "error": str(exc),
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        },
                    )
                    if not recorded:
                        return {
                            "status": "cancelled",
                            "session_id": session_id,
                            "run_id": run_id,
                            "generated": int(state["generated_count"]),
                            "approved": int(state["approved_count"]),
                            "rejected": int(state["rejected_count"]),
                            "failed": len(failures),
                        }
                    failures = state["failures"]
                    assert isinstance(failures, list)
                    continue
                if pending_response is None:
                    return {
                        "status": "cancelled",
                        "session_id": session_id,
                        "run_id": run_id,
                        "generated": int(state["generated_count"]),
                        "approved": int(state["approved_count"]),
                        "rejected": int(state["rejected_count"]),
                        "failed": len(failures),
                    }
                return pending_response

        with _tee_approval_lock():
            try:
                current_session_dir, current_state = self._load_chat_session(
                    session_id
                )
            except ValueError:
                return {
                    "status": "cancelled",
                    "session_id": session_id,
                    "run_id": run_id,
                    "generated": int(state["generated_count"]),
                    "approved": int(state["approved_count"]),
                    "rejected": int(state["rejected_count"]),
                    "failed": len(failures),
                }
            if (
                current_session_dir != session_dir
                or current_state.get("run_id") != run_id
                or current_state.get("pending_candidate") is not None
            ):
                return {
                    "status": "cancelled",
                    "session_id": session_id,
                    "run_id": run_id,
                    "generated": int(current_state.get("generated_count", 0)),
                    "approved": int(current_state.get("approved_count", 0)),
                    "rejected": int(current_state.get("rejected_count", 0)),
                    "failed": len(current_state.get("failures", [])),
                }
            state.clear()
            state.update(current_state)
            failures = state.get("failures", [])
            transparency_failures = state.get("transparency_failures", [])
            assert isinstance(failures, list)
            assert isinstance(transparency_failures, list)
            if failures:
                _write_json_exclusive(
                    self._output_path(catalog_id, run_id, "provider-failures.json"),
                    failures,
                )
            if transparency_failures:
                _write_json_exclusive(
                    self._output_path(
                        catalog_id, run_id, "transparency-failures.json"
                    ),
                    transparency_failures,
                )
            summary = {
                "status": "completed",
                "run_id": run_id,
                "generated": int(state["generated_count"]),
                "approved": int(state["approved_count"]),
                "rejected": int(state["rejected_count"]),
                "failed": len(failures) + len(transparency_failures),
                "failures": failures,
                "transparency_failures": transparency_failures,
            }
            self._presentation_record_path(session_dir).unlink(missing_ok=True)
            shutil.rmtree(session_dir)
        return summary

    def _load_chat_session(self, session_id: str) -> tuple[Path, dict[str, object]]:
        session_dir = self._chat_session_directory(session_id)
        session_path = session_dir / "session.json"
        try:
            state = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("chat approval session is unavailable") from exc
        if not isinstance(state, dict) or state.get("session_id") != session_id:
            raise ValueError("chat approval session is invalid")
        if not re.fullmatch(r"TJD-TEE-\d{3}", str(state.get("catalog_id", ""))):
            raise ValueError("chat approval session catalog ID is invalid")
        if not re.fullmatch(r"[0-9a-f]{32}", str(state.get("run_id", ""))):
            raise ValueError("chat approval session run ID is invalid")
        return session_dir, state

    def _record_chat_failure_if_active(
        self,
        session_dir: Path,
        state: dict[str, object],
        failure: dict[str, object],
    ) -> bool:
        with _tee_approval_lock():
            try:
                current_session_dir, current_state = self._load_chat_session(
                    str(state["session_id"])
                )
            except (KeyError, ValueError):
                return False
            if (
                current_session_dir != session_dir
                or current_state.get("run_id") != state.get("run_id")
                or current_state.get("next_candidate_number")
                != state.get("next_candidate_number")
                or current_state.get("pending_candidate") is not None
            ):
                return False
            failures = current_state.get("failures")
            if not isinstance(failures, list):
                return False
            failures.append(failure)
            self._write_chat_session(current_session_dir, current_state)
            state.clear()
            state.update(current_state)
            return True

    @staticmethod
    def _pending_candidate_path(
        session_dir: Path, pending: dict[str, object]
    ) -> Path:
        candidate_id = str(pending.get("candidate_id", ""))
        image_name = pending.get("image_name")
        if not re.fullmatch(r"[0-9a-f]{8}-\d{2}", candidate_id):
            raise ValueError("pending candidate ID is invalid")
        if not isinstance(image_name, str):
            raise ValueError("pending candidate image is invalid")
        suffix = Path(image_name).suffix.lower()
        if (
            Path(image_name).name != image_name
            or suffix not in _IMAGE_SUFFIXES
            or image_name != f"{candidate_id}{suffix}"
        ):
            raise ValueError("pending candidate image path is invalid")
        image_path = session_dir / image_name
        if (
            _is_reparse_point(image_path)
            or image_path.resolve().parent != session_dir.resolve()
            or not image_path.is_file()
        ):
            raise ValueError("pending candidate image is unavailable")
        return image_path

    @staticmethod
    def _read_verified_pending_candidate(
        pending_path: Path,
        session_dir: Path,
        pending: dict[str, object],
        state: dict[str, object],
    ) -> bytes:
        try:
            expected_fingerprint = pending.get("file_fingerprint")
            if not isinstance(expected_fingerprint, list):
                raise RuntimeError("pending candidate fingerprint is invalid")
            content = _read_file_without_reparse_components(
                pending_path, expected_fingerprint=expected_fingerprint
            )
            current_fingerprint = tuple(expected_fingerprint)
            directory_fingerprint = _stat_fingerprint(session_dir.stat())
            presentation_record = json.loads(
                TeeImageApprovalFlow._presentation_record_path(session_dir).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, RuntimeError) as exc:
            raise ValueError("pending candidate changed after presentation") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("pending candidate changed after presentation") from exc
        if not isinstance(presentation_record, dict):
            raise ValueError("pending candidate changed after presentation")
        signature = presentation_record.get("integrity_hmac_sha256")
        expected_signature = _presentation_hmac(
            state, presentation_record, hashlib.sha256(content).hexdigest()
        )
        if (
            type(signature) is not str
            or not hmac.compare_digest(signature, expected_signature)
            or presentation_record.get("candidate_id") != pending.get("candidate_id")
            or presentation_record.get("directory_fingerprint")
            != list(directory_fingerprint)
            or pending.get("content_sha256") != hashlib.sha256(content).hexdigest()
            or pending.get("file_fingerprint") != list(current_fingerprint)
        ):
            raise ValueError("pending candidate changed after presentation")
        return content

    def decide_chat_candidate(
        self, session_id: str, candidate_id: str, *, decision: str
    ) -> dict[str, object]:
        if decision not in {"y", "n"}:
            raise ValueError("chat decision must be exactly y or n")
        approved_path: Path | None = None
        with _tee_approval_lock():
            session_dir, state = self._load_chat_session(session_id)
            pending = state.get("pending_candidate")
            if not isinstance(pending, dict):
                raise ValueError("chat approval session has no pending candidate")
            if pending.get("candidate_id") != candidate_id:
                raise ValueError("candidate ID does not match the pending candidate")
            pending_path = self._pending_candidate_path(session_dir, pending)
            candidate_bytes = self._read_verified_pending_candidate(
                pending_path, session_dir, pending, state
            )

            if decision == "y":
                entry = self.catalog.read_prompt(str(state["catalog_id"]))
                try:
                    current_revision = int(entry["concept_revision"])
                    approval_revision = int(entry["concept_approval_revision"])
                except (KeyError, TypeError, ValueError) as exc:
                    pending_path.unlink(missing_ok=True)
                    self._presentation_record_path(session_dir).unlink(missing_ok=True)
                    shutil.rmtree(session_dir)
                    raise ValueError("concept approval changed while image was pending") from exc
                if (
                    entry.get("concept_approval_status") != "concept_approved"
                    or current_revision != int(state["concept_revision"])
                    or approval_revision != current_revision
                    or int(entry["image_prompt_revision"])
                    != int(state["image_prompt_revision"])
                    or state.get("prompt_revision") != _PROMPT_REVISION
                ):
                    pending_path.unlink(missing_ok=True)
                    self._presentation_record_path(session_dir).unlink(missing_ok=True)
                    shutil.rmtree(session_dir)
                    raise ValueError(
                        "concept or prompt revision changed while image was pending"
                    )

                catalog_id = str(state["catalog_id"])
                run_id = str(state["run_id"])
                approved_path = self._output_path(
                    catalog_id, run_id, f"{candidate_id}{pending_path.suffix}"
                )
                sidecar_path = self._output_path(
                    catalog_id, run_id, f"{candidate_id}.json"
                )
                sidecar = {
                    "candidate_id": candidate_id,
                    "catalog_id": state["catalog_id"],
                    "concept_revision": current_revision,
                    "provider": pending["provider"],
                    "model": pending["model"],
                    "provider_route": pending["provider_route"],
                    "provider_metadata": pending["provider_metadata"],
                    "provider_metadata_status": pending["provider_metadata_status"],
                    "exact_prompt": pending["exact_prompt"],
                    "image_prompt_revision": int(state["image_prompt_revision"]),
                    "catalog_version": state["catalog_version"],
                    "prompt_revision": _PROMPT_REVISION,
                    "content_sha256": pending["content_sha256"],
                    "approval": "approved",
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_diagnostics": pending["provider_diagnostics"],
                }
                sidecar["integrity_hmac_sha256"] = _approved_sidecar_hmac(
                    sidecar, str(sidecar["content_sha256"])
                )
                approved_created = False
                sidecar_created = False
                try:
                    _write_file_exclusive_without_reparse_components(
                        approved_path, candidate_bytes
                    )
                    approved_created = True
                    persisted_bytes = _read_file_without_reparse_components(
                        approved_path
                    )
                    if hashlib.sha256(persisted_bytes).hexdigest() != pending.get(
                        "content_sha256"
                    ):
                        raise OSError(
                            "approved image readback does not match its pending digest"
                        )
                    _write_json_exclusive(sidecar_path, sidecar)
                    sidecar_created = True
                    self.catalog.approve_exact_image(
                        catalog_id,
                        expected_image_prompt_revision=int(
                            state["image_prompt_revision"]
                        ),
                        expected_concept_revision=current_revision,
                        approved_by_tyler=True,
                    )
                except Exception:
                    if approved_created:
                        approved_path.unlink(missing_ok=True)
                    if sidecar_created:
                        sidecar_path.unlink(missing_ok=True)
                    raise
                state["approved_count"] = int(state["approved_count"]) + 1
            else:
                state["rejected_count"] = int(state["rejected_count"]) + 1

            state["pending_candidate"] = None
            self._write_chat_session(session_dir, state)
            pending_path.unlink(missing_ok=True)
            self._presentation_record_path(session_dir).unlink(missing_ok=True)

        transparency_result: dict[str, object] | None = None
        if approved_path is not None:
            transparency_result = _create_transparent_derivative(
                approved_path, candidate_id
            )
            if transparency_result["status"] == "failed":
                transparency_failures = state["transparency_failures"]
                assert isinstance(transparency_failures, list)
                transparency_failures.append(
                    {
                        "candidate_id": candidate_id,
                        "error": transparency_result.get("error"),
                        "sidecar_path": transparency_result.get("sidecar_path"),
                    }
                )
                with _tee_approval_lock():
                    try:
                        current_session_dir, current_state = self._load_chat_session(
                            session_id
                        )
                    except ValueError:
                        pass
                    else:
                        current_failures = current_state["transparency_failures"]
                        assert isinstance(current_failures, list)
                        current_failures.append(transparency_failures[-1])
                        self._write_chat_session(current_session_dir, current_state)
                        state.clear()
                        state.update(current_state)
        response = self._stage_next_chat_candidate(session_dir, state)
        if transparency_result is not None:
            response["transparency"] = transparency_result
        return response

    def cancel_chat_batch(self, session_id: str) -> dict[str, object]:
        with _tee_approval_lock():
            session_dir, state = self._load_chat_session(session_id)
            pending = state.get("pending_candidate")
            if isinstance(pending, dict):
                self._pending_candidate_path(session_dir, pending).unlink(missing_ok=True)
            self._presentation_record_path(session_dir).unlink(missing_ok=True)
            result = {
                "status": "cancelled",
                "run_id": state["run_id"],
                "generated": int(state["generated_count"]),
                "approved": int(state["approved_count"]),
                "rejected": int(state["rejected_count"]),
                "failed": len(state["failures"]),
            }
            shutil.rmtree(session_dir)
            return result

    def generate_batch(
        self,
        catalog_id: str,
        *,
        count: int = 2,
        decide: Decision | None = None,
    ) -> TeeImageBatchResult:
        """Generate an authorized batch and require a decision for each successful image."""
        _derive_tee_integrity_key()
        if type(count) is not int or not 1 <= count <= _MAX_BATCH_SIZE:
            raise ValueError("candidate count must be between 1 and 4")

        (
            catalog,
            entry,
            concept_revision,
            image_prompt_revision,
            catalog_version,
            exact_prompt,
            has_approved_images,
        ) = self._prepare_generation(catalog_id)

        run_id = uuid.uuid4().hex
        run_dir = self._output_path(catalog_id, run_id)
        approved: list[TeeImageCandidate] = []
        rejected_count = 0
        failures: list[dict[str, object]] = []
        transparency_failures: list[dict[str, object]] = []
        decision_callback = decide if decide is not None else _interactive_decision

        for candidate_number in range(1, count + 1):
            candidate_id = f"{run_id[:8]}-{candidate_number:02d}"
            with _tee_approval_lock():
                if not self._catalog_generation_is_current(
                    catalog_id, concept_revision, image_prompt_revision
                ):
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": "concept or image prompt changed before the next provider attempt",
                            "diagnostics": [],
                        }
                    )
                    break
            candidate_prompt = _compose_candidate_prompt(exact_prompt, candidate_number)
            with tempfile.TemporaryDirectory(prefix="tee-image-candidate-") as temporary_dir:
                temporary_root = Path(temporary_dir)
                try:
                    result = self.cascade.generate(candidate_prompt, output_dir=temporary_root)
                    provider, model, provider_route = _validated_provider_tuple(result)
                except Exception as exc:
                    diagnostics = getattr(exc, "diagnostics", ())
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": str(exc),
                            "diagnostics": [_diagnostic_dict(item) for item in diagnostics],
                        }
                    )
                    continue

                source_path = Path(result.path)
                source_bytes: bytes | None = None
                source_identity: os.stat_result | None = None
                source_parent_fingerprint: tuple[int, int, int, int, int] | None = None
                content_mismatch = False
                try:
                    if (
                        source_path.is_file()
                        and source_path.suffix.lower() in _IMAGE_SUFFIXES
                        and source_path.resolve(strict=True).is_relative_to(
                            temporary_root.resolve()
                        )
                    ):
                        with source_path.open("rb") as source_file:
                            opened_stat = os.fstat(source_file.fileno())
                            resolved_path = source_path.resolve(strict=True)
                            if (
                                resolved_path.is_relative_to(temporary_root.resolve())
                                and os.path.samestat(opened_stat, resolved_path.stat())
                            ):
                                content = source_file.read()
                                if _matches_image_signature(
                                    source_path.suffix.lower(), content
                                ):
                                    source_bytes = content
                                    source_identity = opened_stat
                                    _pin_directory_mtime_for_mutation_detection(
                                        source_path.parent
                                    )
                                    source_parent_fingerprint = _stat_fingerprint(
                                        source_path.parent.stat()
                                    )
                                else:
                                    content_mismatch = True
                except (OSError, RuntimeError):
                    pass

                if source_identity is None or source_bytes is None:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": (
                                "image file content does not match its extension"
                                if content_mismatch
                                else "image cascade returned a missing, unsupported, or out-of-directory image file"
                            ),
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    continue

                with _tee_approval_lock():
                    if not self._catalog_generation_is_current(
                        catalog_id, concept_revision, image_prompt_revision
                    ):
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": "concept or image prompt changed while the provider was generating",
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        break

                candidate = TeeImageCandidate(
                    candidate_id=candidate_id,
                    path=source_path,
                    provider=provider,
                    model=model,
                    exact_prompt=candidate_prompt,
                    provider_route=provider_route,
                )
                provider_metadata, provider_metadata_status = _provider_metadata_record(
                    result
                )
                if not decision_callback(candidate):
                    rejected_count += 1
                    continue

                with _tee_approval_lock():
                    if not self._catalog_generation_is_current(
                        catalog_id, concept_revision, image_prompt_revision
                    ):
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": "concept or image prompt changed during candidate review",
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        break
                    candidate_path_is_unchanged = False
                    candidate_content_is_unchanged = False
                    try:
                        resolved_path = source_path.resolve(strict=True)
                        current_stat = resolved_path.stat()
                        candidate_path_is_unchanged = (
                            resolved_path.is_relative_to(temporary_root.resolve())
                            and os.path.samestat(source_identity, current_stat)
                            and source_parent_fingerprint is not None
                            and _stat_fingerprint(source_path.parent.stat())
                            == source_parent_fingerprint
                        )
                    except (OSError, RuntimeError):
                        candidate_path_is_unchanged = False
                    if candidate_path_is_unchanged:
                        try:
                            current_source_bytes = _read_file_without_reparse_components(
                                resolved_path,
                                expected_fingerprint=_stat_fingerprint(source_identity),
                            )
                            candidate_content_is_unchanged = (
                                _stat_fingerprint(current_stat)
                                == _stat_fingerprint(source_identity)
                                and current_source_bytes == source_bytes
                            )
                        except (OSError, RuntimeError):
                            candidate_content_is_unchanged = False
                    if not candidate_path_is_unchanged:
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": "image candidate changed or escaped the generation directory during approval",
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        continue
                    if not candidate_content_is_unchanged:
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": "image candidate content changed during approval",
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        continue

                    suffix = source_path.suffix.lower()
                    approved_path = self._output_path(
                        catalog_id, run_id, f"{candidate_id}{suffix}"
                    )
                    sidecar_path = self._output_path(
                        catalog_id, run_id, f"{candidate_id}.json"
                    )
                    sidecar = {
                        "candidate_id": candidate_id,
                        "catalog_id": catalog_id,
                        "concept_revision": concept_revision,
                        "provider": candidate.provider,
                        "model": candidate.model,
                        "provider_route": candidate.provider_route,
                        "provider_metadata": provider_metadata,
                        "provider_metadata_status": provider_metadata_status,
                        "exact_prompt": candidate_prompt,
                        "image_prompt_revision": image_prompt_revision,
                        "catalog_version": catalog_version,
                        "prompt_revision": _PROMPT_REVISION,
                        "content_sha256": hashlib.sha256(source_bytes).hexdigest(),
                        "approval": "approved",
                        "approved_at": datetime.now(timezone.utc).isoformat(),
                        "provider_diagnostics": [
                            _diagnostic_dict(item)
                            for item in getattr(result, "diagnostics", ())
                        ],
                    }
                    approved_created = False
                    sidecar_created = False
                    try:
                        _write_file_exclusive_without_reparse_components(
                            approved_path, source_bytes
                        )
                        approved_created = True
                        approved_content = _read_file_without_reparse_components(
                            approved_path
                        )
                        if approved_content != source_bytes:
                            raise OSError("approved image changed while being written")
                        sidecar["content_sha256"] = hashlib.sha256(
                            approved_content
                        ).hexdigest()
                        sidecar["integrity_hmac_sha256"] = _approved_sidecar_hmac(
                            sidecar, str(sidecar["content_sha256"])
                        )
                        _write_json_exclusive(sidecar_path, sidecar)
                        sidecar_created = True
                        self.catalog.approve_exact_image(
                            catalog_id,
                            expected_image_prompt_revision=image_prompt_revision,
                            expected_concept_revision=concept_revision,
                            approved_by_tyler=True,
                        )
                    except FileExistsError:
                        if approved_created:
                            approved_path.unlink(missing_ok=True)
                        if sidecar_created:
                            sidecar_path.unlink(missing_ok=True)
                        failures.append(
                            {
                                "candidate_id": candidate_id,
                                "error": "approved image or sidecar destination already exists",
                                "diagnostics": [
                                    _diagnostic_dict(item)
                                    for item in getattr(result, "diagnostics", ())
                                ],
                            }
                        )
                        continue
                    except Exception:
                        if approved_created:
                            approved_path.unlink(missing_ok=True)
                        if sidecar_created:
                            sidecar_path.unlink(missing_ok=True)
                        raise
                approved.append(
                    TeeImageCandidate(
                        candidate_id=candidate_id,
                        path=approved_path,
                        provider=candidate.provider,
                        model=candidate.model,
                        exact_prompt=exact_prompt,
                        provider_route=candidate.provider_route,
                    )
                )
                transparency_result = _create_transparent_derivative(
                    approved_path, candidate_id
                )
                if transparency_result["status"] == "failed":
                    transparency_failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": transparency_result.get("error"),
                            "sidecar_path": transparency_result.get("sidecar_path"),
                        }
                    )

        if failures:
            _write_json_exclusive(
                self._output_path(catalog_id, run_id, "provider-failures.json"),
                failures,
            )
        if transparency_failures:
            _write_json_exclusive(
                self._output_path(
                    catalog_id, run_id, "transparency-failures.json"
                ),
                transparency_failures,
            )

        return TeeImageBatchResult(
            run_id=run_id,
            approved=tuple(approved),
            rejected_count=rejected_count,
            failures=tuple([*failures, *transparency_failures]),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-id")
    parser.add_argument("--count", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--chat-start", action="store_true")
    mode.add_argument("--chat-decide", action="store_true")
    mode.add_argument("--chat-cancel", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--candidate-id")
    parser.add_argument("--decision", choices=("y", "n"))
    args = parser.parse_args(argv)

    connection = _live_connection()
    try:
        flow = TeeImageApprovalFlow(
            TeePromptCatalog(connection),
            _OUTPUT_ROOT,
            pending_root=_PENDING_ROOT,
        )
        if args.chat_start:
            if not args.catalog_id or args.session_id or args.candidate_id or args.decision:
                parser.error("--chat-start requires --catalog-id and no decision fields")
            result = flow.start_chat_batch(
                args.catalog_id,
                count=args.count if args.count is not None else 2,
            )
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.chat_decide:
            if args.catalog_id or args.count is not None or not all(
                (args.session_id, args.candidate_id, args.decision)
            ):
                parser.error("--chat-decide requires --session-id, --candidate-id, and --decision")
            result = flow.decide_chat_candidate(
                args.session_id,
                args.candidate_id,
                decision=args.decision,
            )
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.chat_cancel:
            if (
                args.catalog_id
                or args.count is not None
                or args.candidate_id
                or args.decision
                or not args.session_id
            ):
                parser.error("--chat-cancel requires only --session-id")
            result = flow.cancel_chat_batch(args.session_id)
            print(json.dumps(result, ensure_ascii=False))
            return 0

        if not args.catalog_id or args.session_id or args.candidate_id or args.decision:
            parser.error("--catalog-id is required for terminal-interactive generation")
        result = flow.generate_batch(
            args.catalog_id,
            count=args.count if args.count is not None else 2,
        )
        failure_count = len(result.failures)
        failure_label = "failure" if failure_count == 1 else "failures"
        print(
            f"Run {result.run_id}: {len(result.approved)} approved, "
            f"{result.rejected_count} rejected, {failure_count} candidate {failure_label}"
        )
        for failure in result.failures:
            print(
                f"{failure.get('candidate_id', 'unknown candidate')}: "
                f"{failure.get('error', 'unspecified failure')}"
            )
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())