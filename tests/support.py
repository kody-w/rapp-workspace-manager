"""Synthetic test fixtures live beneath this repository, never in OS temp dirs."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import uuid
from pathlib import Path
from unittest import mock


@contextlib.contextmanager
def fixture_directory():
    parent = Path(".test-fixtures")
    parent.mkdir(exist_ok=True)
    path = parent / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path.absolute()
    finally:
        shutil.rmtree(path)
        try:
            parent.rmdir()
        except OSError:
            pass


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def snapshot(root):
    return {
        str(path.relative_to(root)): (
            path.lstat().st_mode, path.lstat().st_size, path.lstat().st_mtime_ns,
            path.lstat().st_ctime_ns,
            os.readlink(path) if path.is_symlink() else (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            ),
        )
        for path in sorted(root.rglob("*"))
    }


@contextlib.contextmanager
def metadata_guard(roots, allowed_reads):
    """Deny native/source content reads and writes, including descriptor I/O."""
    roots = [Path(root).absolute() for root in roots]
    allowed = {str(Path(path).absolute()) for path in allowed_reads}
    opened, fd_paths = [], {}
    real_open, real_builtin, real_io = os.open, open, io.open

    def location(path, dir_fd=None):
        if isinstance(path, int):
            return fd_paths.get(path)
        path = Path(path)
        if not path.is_absolute() and dir_fd in fd_paths:
            path = fd_paths[dir_fd] / path
        return path.absolute()

    def protected(path):
        return path is not None and any(path == root or root in path.parents for root in roots)

    def check(path, writes=False, directory=False):
        if protected(path):
            if writes:
                raise AssertionError(f"native/source write: {path}")
            if not directory and str(path) not in allowed:
                raise AssertionError(f"non-metadata read: {path}")
            if not directory:
                opened.append(str(path))

    def os_open(path, flags, mode=0o777, *, dir_fd=None):
        target = location(path, dir_fd)
        check(
            target, writes=bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)),
            directory=bool(flags & os.O_DIRECTORY),
        )
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        fd_paths[fd] = target
        return fd

    def ordinary(real):
        def wrapped(path, mode="r", *args, **kwargs):
            if not isinstance(path, int):
                check(location(path), writes=any(char in mode for char in "wax+"))
            return real(path, mode, *args, **kwargs)
        return wrapped

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("os.open", os_open))
        stack.enter_context(mock.patch("os.supports_dir_fd", os.supports_dir_fd | {os_open}))
        stack.enter_context(mock.patch("builtins.open", ordinary(real_builtin)))
        stack.enter_context(mock.patch("io.open", ordinary(real_io)))
        for name in ("mkdir", "unlink", "remove", "rmdir", "chmod", "truncate"):
            original = getattr(os, name)

            def mutation(path, *args, _original=original, **kwargs):
                check(location(path, kwargs.get("dir_fd")), writes=True)
                return _original(path, *args, **kwargs)

            stack.enter_context(mock.patch.object(os, name, mutation))
        for name in ("replace", "rename"):
            original = getattr(os, name)

            def rename(src, dst, *args, _original=original, **kwargs):
                check(location(src, kwargs.get("src_dir_fd")), writes=True)
                check(location(dst, kwargs.get("dst_dir_fd")), writes=True)
                return _original(src, dst, *args, **kwargs)

            stack.enter_context(mock.patch.object(os, name, rename))
        yield opened
