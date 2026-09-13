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
    if not isinstance(text, str) or not text or len(text) > 4096 or any(ord(c) < 32 for c in text):
        raise RoutingError("invalid-path")
    expanded = os.path.expanduser(text)
    # POSIX permits implementation-defined "//" roots. This application accepts
    # only the ordinary local root, never an alternate root namespace.
    if expanded.startswith("/"):
        expanded = "/" + expanded.lstrip("/")
    path = Path(expanded)
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
def _walk_directory(path, create=False, missing_ok=False):
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
        complete = True
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not missing_ok:
                    raise
                complete = False
                break
            os.close(fd)
            fd = child
        yield fd, complete
    except OSError as error:
        raise io_error(error) from None
    finally:
        if fd is not None:
            os.close(fd)


@contextlib.contextmanager
def directory_fd(path, create=False):
    with _walk_directory(path, create=create) as (fd, _):
        yield fd


def filesystem_identity(info):
    return validate_filesystem_identity([info.st_dev, info.st_ino])


def validate_filesystem_identity(value):
    if (
        not isinstance(value, list) or len(value) != 2
        or type(value[0]) is not int or value[0] < 0
        or type(value[1]) is not int or value[1] <= 0
    ):
        raise RoutingError("filesystem-identity-mismatch")
    return value


def directory_identity(path):
    with directory_fd(path) as fd:
        return filesystem_identity(os.fstat(fd))


def _physical_ancestors(fd):
    """Inspect kernel parent links of a pinned directory, not lexical prefixes."""
    current = os.dup(fd)
    ancestors = []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        for _ in range(128):
            identity = filesystem_identity(os.fstat(current))
            if identity in ancestors:
                raise RoutingError("filesystem-ancestry-cycle")
            ancestors.append(identity)
            parent = os.open("..", flags, dir_fd=current)
            try:
                parent_identity = filesystem_identity(os.fstat(parent))
            except BaseException:
                os.close(parent)
                raise
            if parent_identity == identity:
                os.close(parent)
                return ancestors
            os.close(current)
            current = parent
        raise RoutingError("depth-bound")
    finally:
        os.close(current)


def directory_info(path, missing_ok=False):
    path = absolute_path(path)
    with _walk_directory(path, missing_ok=missing_ok) as (fd, complete):
        ancestors = _physical_ancestors(fd)
        return {
            "path": str(path),
            "identity": ancestors[0] if complete else None,
            "ancestors": ancestors,
        }


def same_directory(left, right):
    a = directory_info(left, missing_ok=True)
    b = directory_info(right, missing_ok=True)
    return a["identity"] is not None and a["identity"] == b["identity"]


def directories_overlap(left, right):
    a = directory_info(left, missing_ok=True)
    b = directory_info(right, missing_ok=True)
    return (
        a["identity"] is not None and a["identity"] in b["ancestors"]
        or b["identity"] is not None and b["identity"] in a["ancestors"]
    )


def same_location(left, right):
    a, b = absolute_path(left), absolute_path(right)
    return a == b or same_directory(a, b)


def unique_directories(paths):
    found = {}
    for path in map(absolute_path, paths):
        key = tuple(directory_identity(path))
        found.setdefault(key, path)
    return list(found.values())


@contextlib.contextmanager
def regular_fd(path):
    path = absolute_path(path)
    with directory_fd(path.parent) as parent:
        fd = None
        try:
            fd = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise RoutingError("not-regular-metadata")
            if info.st_nlink != 1:
                raise RoutingError("hardlink-refused")
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
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise RoutingError("hardlink-refused")
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


def resolve_protected_boundary(value):
    root = value["path"] if isinstance(value, dict) else value
    saved = value.get("identity") if isinstance(value, dict) else None
    historical = value.get("historical", False) if isinstance(value, dict) else False
    if type(historical) is not bool:
        raise RoutingError("invalid-protection-boundary")
    if saved is not None:
        validate_filesystem_identity(saved)
    try:
        current = directory_info(root, missing_ok=True)
    except RoutingError:
        if not historical:
            raise
        current = None
    # Historical names are evidence about an object, not protection claims over
    # whatever now occupies that spelling. The saved object ID remains protected.
    if historical and (saved is None or current is None or current["identity"] != saved):
        current = None
    return saved, current


def protected_local(path, profile_roots=(), *, candidate_info=None):
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
    candidate = candidate_info or directory_info(path, missing_ok=True)
    home = directory_info(Path.home(), missing_ok=True)
    if candidate["identity"] is not None and candidate["identity"] in home["ancestors"]:
        return True
    for value in profile_roots:
        saved_identity, protected = resolve_protected_boundary(value)
        if saved_identity is not None:
            if saved_identity in candidate["ancestors"]:
                return True
        if protected is None:
            continue
        if (
            protected["identity"] is not None and protected["identity"] in candidate["ancestors"]
            or candidate["identity"] is not None and candidate["identity"] in protected["ancestors"]
        ):
            return True
    return False


def verified_directory_info(value, profile_roots=(), expected_identity=None):
    path = native_path(value)
    if path is None:
        return None
    try:
        info = directory_info(path)
        if expected_identity is not None and info["identity"] != expected_identity:
            return None
        if not protected_local(path, profile_roots, candidate_info=info):
            return info
    except RoutingError:
        return None


def verified_directory(value, profile_roots=(), expected_identity=None):
    info = verified_directory_info(value, profile_roots, expected_identity)
    return info["path"] if info is not None else None


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
    existing = safe_stat(absolute_path(workspace) / ".routing.lock", missing_ok=True)
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise RoutingError("unsafe-manager-output")
    with directory_fd(workspace) as parent:
        fd = None
        try:
            fd = os.open(
                ".routing.lock", os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600, dir_fd=parent,
            )
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise RoutingError("unsafe-manager-output")
            if info.st_nlink != 1:
                raise RoutingError("hardlink-refused")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except OSError as error:
            raise io_error(error) from None
        finally:
            if fd is not None:
                os.close(fd)
