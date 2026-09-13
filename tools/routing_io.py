"""Bounded, descriptor-relative I/O for manager metadata, never routed content."""

import contextlib
import errno
import json
import os
import stat
import time
import uuid
from pathlib import Path


class RoutingError(Exception):
    """A deliberately content-free error suitable for a private routing catalog."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Limits:
    DEFAULTS = {
        "max_entries": 150000,
        "batch_size": 1000,
        "max_file_bytes": 2 * 1024 * 1024,
        "max_total_bytes": 16 * 1024 * 1024,
        "max_seconds": 10.0,
    }
    CEILINGS = {
        "max_entries": 200000,
        "batch_size": 10000,
        "max_file_bytes": 8 * 1024 * 1024,
        "max_total_bytes": 64 * 1024 * 1024,
        "max_seconds": 60.0,
    }

    def __init__(self, **values):
        if set(values) - self.DEFAULTS.keys():
            raise RoutingError("unknown-limit")
        for key, default in self.DEFAULTS.items():
            value = values.get(key, default)
            numeric = (int, float) if key == "max_seconds" else (int,)
            if (
                isinstance(value, bool)
                or not isinstance(value, numeric)
                or not 0 < value <= self.CEILINGS[key]
            ):
                raise RoutingError("invalid-limit")
            setattr(self, key, value)

    def as_dict(self):
        return {key: getattr(self, key) for key in self.DEFAULTS}


class Budget:
    def __init__(self, limits=None, clock=None):
        self.limits = limits or Limits()
        self.clock = clock or time.monotonic
        self.deadline = self.clock() + self.limits.max_seconds
        self.entries = 0
        self.bytes = 0

    def check(self):
        if self.clock() >= self.deadline:
            raise RoutingError("time-bound")

    def entry(self):
        self.check()
        self.entries += 1
        if self.entries > self.limits.max_entries:
            raise RoutingError("count-bound")

    def consume(self, size):
        self.check()
        self.bytes += size
        if self.bytes > self.limits.max_total_bytes:
            raise RoutingError("byte-bound")


def absolute_path(value):
    if not isinstance(value, (str, os.PathLike)):
        raise RoutingError("invalid-path")
    text = os.fspath(value)
    if not text or len(text) > 4096 or any(ord(c) < 32 for c in text):
        raise RoutingError("invalid-path")
    path = Path(os.path.expanduser(text))
    if ".." in path.parts or len(path.parts) > 128:
        raise RoutingError("path-traversal")
    return Path(os.path.abspath(path))


def native_path(value):
    """Native relative/opaque references are not converted into local paths."""
    if not isinstance(value, str) or not Path(value).is_absolute():
        return None
    try:
        return absolute_path(value)
    except RoutingError:
        return None


def stamp(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def io_error(error):
    if error.errno in (errno.ELOOP, errno.ENOTDIR):
        return RoutingError("symlink-or-not-directory")
    if error.errno in (errno.EAGAIN, errno.EBUSY, errno.EWOULDBLOCK):
        return RoutingError("native-busy")
    if error.errno == errno.ENOENT:
        return RoutingError("metadata-missing")
    return RoutingError("metadata-unreadable")


@contextlib.contextmanager
def directory_fd(path, create=False):
    path = absolute_path(path)
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
    ):
        raise RoutingError("safe-io-unavailable")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(path.anchor, flags)
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    except OSError as error:
        raise io_error(error) from None
    finally:
        if fd is not None:
            os.close(fd)


@contextlib.contextmanager
def regular_fd(path):
    path = absolute_path(path)
    with directory_fd(path.parent) as parent:
        fd = None
        try:
            fd = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RoutingError("not-regular-metadata")
            yield fd
        except OSError as error:
            raise io_error(error) from None
        finally:
            if fd is not None:
                os.close(fd)


def safe_stat(path, missing_ok=False):
    path = absolute_path(path)
    with directory_fd(path.parent) as parent:
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise RoutingError("metadata-missing") from None
        except OSError as error:
            raise io_error(error) from None
        if stat.S_ISLNK(info.st_mode):
            raise RoutingError("symlink-refused")
        return info


def read_bytes(path, budget=None, max_bytes=None):
    if budget is None:
        budget = Budget()
        if max_bytes is not None:
            budget.limits.max_total_bytes = max_bytes
    maximum = max_bytes if max_bytes is not None else budget.limits.max_file_bytes
    budget.check()
    with regular_fd(path) as fd:
        before = stamp(os.fstat(fd))
        if before[2] > maximum:
            raise RoutingError("file-size-bound")
        chunks = []
        size = 0
        while True:
            budget.check()
            chunk = os.read(fd, min(65536, maximum + 1 - size))
            if not chunk:
                break
            budget.consume(len(chunk))
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise RoutingError("file-size-bound")
        if stamp(os.fstat(fd)) != before:
            raise RoutingError("metadata-changed")
        budget.check()
        return b"".join(chunks)


def read_json(path, budget=None, max_bytes=None):
    try:
        return json.loads(
            read_bytes(path, budget, max_bytes).decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise RoutingError("malformed-metadata") from None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError("non-JSON numeric constant")


def child_directories(path, budget):
    """One level only; even ignored files count against the enumeration budget."""
    names = []
    with directory_fd(path) as fd:
        before = stamp(os.fstat(fd))
        with os.scandir(fd) as entries:
            for entry in entries:
                budget.entry()
                if entry.is_dir(follow_symlinks=False):
                    names.append(entry.name)
        if stamp(os.fstat(fd)) != before:
            raise RoutingError("metadata-changed")
    return sorted(names), before


NATIVE_COMPONENTS = {".copilot", ".claude", ".hermes", ".scout", ".grokbot", ".grok"}


def protected_local(path, profile_roots=()):
    path = absolute_path(path)
    lowered = [part.casefold() for part in path.parts]
    if any(part in NATIVE_COMPONENTS for part in lowered):
        return True
    if any(part.endswith(".app") for part in lowered):
        return True
    if (
        any(part in ("application support", "caches", "preferences", "saved application state") for part in lowered)
        and any("grokbot" in part or part == "grok" or part.startswith("com.grok.") for part in lowered)
    ):
        return True
    if path == Path(path.anchor) or path == Path.home():
        return True
    return any(
        path == root or root in path.parents or path in root.parents
        for root in map(absolute_path, profile_roots)
    )


def verified_directory(value, profile_roots=()):
    path = native_path(value)
    if path is None:
        return None
    if protected_local(path, profile_roots):
        return None
    try:
        with directory_fd(path):
            return str(path)
    except RoutingError:
        return None


def ensure_output(path):
    path = absolute_path(path)
    with directory_fd(path.parent):
        info = safe_stat(path, missing_ok=True)
        if info is not None and not stat.S_ISREG(info.st_mode):
            raise RoutingError("unsafe-manager-output")
    return path


def atomic_text(path, text):
    """Same-directory exclusive staging and rename, without following any links."""
    path = ensure_output(path)
    name = f".{path.name}.{uuid.uuid4().hex}.pending"
    with directory_fd(path.parent) as parent:
        fd = None
        try:
            fd = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=parent,
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                fd = None
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                pass


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


@contextlib.contextmanager
def manager_lock(workspace):
    try:
        import fcntl
    except ImportError:
        raise RoutingError("safe-io-unavailable") from None
    with directory_fd(workspace) as parent:
        fd = None
        try:
            fd = os.open(
                ".routing.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600, dir_fd=parent,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RoutingError("unsafe-manager-output")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except OSError as error:
            raise io_error(error) from None
        finally:
            if fd is not None:
                os.close(fd)
