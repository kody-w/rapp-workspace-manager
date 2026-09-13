"""Explicit native metadata adapters. Catalog observations are not owner selection."""

import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path

from routing_io import (
    Budget, Limits, RoutingError, absolute_path, child_directories, directory_fd,
    directory_identity, directory_info, native_path, read_bytes, read_json,
    regular_fd, safe_stat, stamp, unique_directories, validate_filesystem_identity,
    verified_directory_info,
)


PROVIDERS = ("copilot", "claude", "hermes", "scout", "grokbot")
POINTER_VERSION = 2
MAX_CATALOG_BYTES = 128 * 1024 * 1024
UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
COPILOT_FIELDS = {
    "id", "cwd", "git_root", "repository", "host_type", "branch", "client_name",
    "created_at", "updated_at",
}
HERMES_TABLES = {
    "sessions": ("hermes-session", {
        "id", "parent_session_id", "project_id", "folder_id", "cwd",
        "created_at", "updated_at",
    }),
    "projects": ("hermes-project", {"id", "path", "created_at", "updated_at"}),
    "folders": ("hermes-folder", {"id", "project_id", "path", "created_at", "updated_at"}),
    "project_folders": (
        "hermes-folder", {"id", "project_id", "path", "created_at", "updated_at"}
    ),
}
COMMON = {"pointer_version", "pointer_type", "pointer_id", "provider", "profileRoot", "profileIdentity"}
POINTER_FIELDS = {
    "copilot-session": COMMON | {"nativeSessionId", "metadata", "sourceStamp", "availability"},
    "claude-project": COMMON | {
        "nativeRoot", "nativeKey", "indexVersion", "originalPath",
        "pathAssociations", "availability",
    },
    "hermes-session": COMMON | {"nativeTable", "nativeId", "schemaVersion", "metadata"},
    "hermes-project": COMMON | {"nativeTable", "nativeId", "schemaVersion", "metadata"},
    "hermes-folder": COMMON | {"nativeTable", "nativeId", "schemaVersion", "metadata"},
    "scout-workspace": COMMON | {"nativeVersion", "workspaceId", "providerId", "rootId"},
}


def text(value, optional=False):
    if value is None and optional:
        return None
    if (
        not isinstance(value, str) or (not value and not optional)
        or any(ord(c) < 32 for c in value)
    ):
        raise RoutingError("schema-mismatch")
    try:
        if len(value.encode("utf-8")) > 4096:
            raise RoutingError("schema-mismatch")
    except UnicodeError:
        raise RoutingError("schema-mismatch") from None
    return value


def scalar(value):
    if value is None or (type(value) in (int, float) and abs(value) < 10 ** 30):
        return value
    return text(value, optional=True)


def legacy_pointer_id(provider, profile_root, native_kind, native_id):
    key = json.dumps(
        [provider, str(profile_root), native_kind, native_id],
        ensure_ascii=True, separators=(",", ":"), allow_nan=False,
    )
    return provider + ":" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def routing_id(provider, identity, native_kind, native_id):
    validate_filesystem_identity(identity)
    key = json.dumps(
        ["filesystem-pointer/2", provider, identity, native_kind, native_id],
        ensure_ascii=True, separators=(",", ":"), allow_nan=False,
    )
    return provider + ":" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def pointer_id(provider, profile_root, native_kind, native_id, *, profile_identity=None):
    identity = directory_identity(profile_root) if profile_identity is None else profile_identity
    return routing_id(provider, identity, native_kind, native_id)


def grokbot_observation_id(root, *, profile_identity=None):
    return pointer_id("grokbot", root, "app-observation", None, profile_identity=profile_identity)


def pointer(provider, root, kind, native_id, *, profile_identity=None, **metadata):
    identity = directory_identity(root) if profile_identity is None else profile_identity
    value = {
        "pointer_version": POINTER_VERSION,
        "pointer_type": kind,
        "pointer_id": routing_id(provider, identity, kind, native_id),
        "provider": provider,
        "profileRoot": str(absolute_path(root)),
        "profileIdentity": identity,
        **metadata,
    }
    validate_pointer(value)
    return value


def native_key(value):
    value = text(value)
    if value in (".", "..") or "/" in value or "\\" in value:
        raise RoutingError("path-traversal")
    return value


def validate_pointer(value):
    if not isinstance(value, dict):
        raise RoutingError("pointer-schema-mismatch")
    kind = value.get("pointer_type")
    version = value.get("pointer_version")
    if (
        not isinstance(kind, str) or kind not in POINTER_FIELDS
        or type(version) is not int or version not in (1, POINTER_VERSION)
        or set(value) != (POINTER_FIELDS[kind] - ({"profileIdentity"} if version == 1 else set()))
    ):
        raise RoutingError("pointer-schema-mismatch")
    root = text(value["profileRoot"])
    if native_path(root) is None or version == 2 and str(absolute_path(root)) != root:
        raise RoutingError("pointer-schema-mismatch")
    if version == 2:
        validate_filesystem_identity(value["profileIdentity"])
    if kind == "copilot-session":
        provider = "copilot"
        identity = text(value["nativeSessionId"])
        metadata = value["metadata"]
        if not UUID.fullmatch(identity) or not isinstance(metadata, dict):
            raise RoutingError("pointer-schema-mismatch")
        if set(metadata) - COPILOT_FIELDS:
            raise RoutingError("pointer-schema-mismatch")
        for field in metadata.values():
            text(field, optional=True)
        if metadata.get("id") is not None and metadata["id"].casefold() != identity.casefold():
            raise RoutingError("session-identity-mismatch")
        if value["availability"] not in ("metadata", "missing-metadata"):
            raise RoutingError("pointer-schema-mismatch")
        source_stamp = value["sourceStamp"]
        if source_stamp is not None and (
            not isinstance(source_stamp, list) or len(source_stamp) != 5
            or any(type(n) is not int or n < 0 for n in source_stamp)
        ):
            raise RoutingError("pointer-schema-mismatch")
        if (
            value["availability"] == "missing-metadata" and (metadata or source_stamp is not None)
            or value["availability"] == "metadata" and (not metadata or source_stamp is None)
        ):
            raise RoutingError("pointer-schema-mismatch")
    elif kind == "claude-project":
        provider = "claude"
        identity = native_key(value["nativeKey"])
        if value["nativeRoot"] != str(Path(root) / "projects"):
            raise RoutingError("pointer-schema-mismatch")
        if value["indexVersion"] is not None and (
            type(value["indexVersion"]) is not int or value["indexVersion"] != 1
        ):
            raise RoutingError("pointer-schema-mismatch")
        text(value["originalPath"], optional=True)
        if value["availability"] not in ("indexed", "missing-index"):
            raise RoutingError("pointer-schema-mismatch")
        if not isinstance(value["pathAssociations"], list):
            raise RoutingError("pointer-schema-mismatch")
        for association in value["pathAssociations"]:
            if not isinstance(association, dict) or set(association) != {"originalPath", "projectPath"}:
                raise RoutingError("pointer-schema-mismatch")
            for field in association.values():
                text(field, optional=True)
        if (
            value["availability"] == "missing-index"
            and (value["indexVersion"] is not None or value["originalPath"] is not None or value["pathAssociations"])
        ) or (value["availability"] == "indexed" and value["indexVersion"] != 1):
            raise RoutingError("pointer-schema-mismatch")
    elif kind.startswith("hermes-"):
        provider = "hermes"
        table = value["nativeTable"]
        metadata = value["metadata"]
        if (
            not isinstance(table, str) or table not in HERMES_TABLES or HERMES_TABLES[table][0] != kind
            or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 0
            or not isinstance(metadata, dict) or set(metadata) - HERMES_TABLES[table][1]
        ):
            raise RoutingError("pointer-schema-mismatch")
        identity = [table, value["nativeId"]]
        if type(value["nativeId"]) not in (str, int) or metadata.get("id") != value["nativeId"]:
            raise RoutingError("pointer-schema-mismatch")
        if isinstance(value["nativeId"], str):
            text(value["nativeId"])
        for field in metadata.values():
            scalar(field)
        for field in ("cwd", "path"):
            if field in metadata:
                text(metadata[field], optional=True)
    else:
        provider = "scout"
        identity = text(value["workspaceId"])
        if type(value["nativeVersion"]) is not int or value["nativeVersion"] != 3:
            raise RoutingError("pointer-schema-mismatch")
        text(value["providerId"])
        text(value["rootId"])
    expected = legacy_pointer_id(provider, root, kind, identity) if version == 1 else routing_id(
        provider, value["profileIdentity"], kind, identity
    )
    if value["provider"] != provider or value["pointer_id"] != expected:
        raise RoutingError("pointer-identity-mismatch")
    return value


def local_paths(value, profile_roots=()):
    """Resolve only explicit native references, never names, slugs or breadcrumbs."""
    validate_pointer(value)
    kind = value["pointer_type"]
    if kind == "copilot-session" and value["pointer_version"] == 1:
        return []
    candidates = []
    if kind == "copilot-session":
        metadata = value["metadata"]
        candidates = [metadata.get("cwd") or metadata.get("git_root")]
    elif kind == "claude-project":
        candidates = [value["originalPath"]]
        for association in value["pathAssociations"]:
            candidates.extend([association["originalPath"], association["projectPath"]])
    elif kind.startswith("hermes-"):
        field = "cwd" if kind == "hermes-session" else "path"
        candidates = [value["metadata"].get(field)]
    elif kind == "scout-workspace" and value["providerId"] == "local":
        candidates = [value["rootId"]]
    roots = list(profile_roots) + [{
        "path": value["profileRoot"], "identity": value.get("profileIdentity"),
    }]
    found = {}
    for candidate in candidates:
        info = verified_directory_info(candidate, roots)
        if info is not None:
            found.setdefault(tuple(info["identity"]), info["path"])
    return sorted(found.values())


def describe(value):
    kind = value["pointer_type"]
    if kind == "copilot-session":
        return value["nativeSessionId"]
    if kind == "claude-project":
        return value["nativeKey"]
    if kind.startswith("hermes-"):
        return f"{value['nativeTable']}:{value['nativeId']}"
    return f"{value['workspaceId']} ({value['providerId']})"


def routing_hint(value):
    if value["pointer_type"] == "scout-workspace" and value["providerId"] != "local":
        return f"nonlocal: {value['rootId']}"
    if value["pointer_type"] == "claude-project":
        return value["availability"]
    if value["pointer_type"] == "copilot-session":
        if value["pointer_version"] == 1:
            return "refresh required: legacy YAML reader"
        return "cwd/git_root reference" if value["metadata"].get("cwd") or value["metadata"].get("git_root") else "unknown cwd"
    if value["pointer_type"].startswith("hermes-"):
        return "native path reference" if value["metadata"].get("path") or value["metadata"].get("cwd") else "unknown path"
    return "local provider reference (verified for editor only)"


def _yaml_metadata(raw):
    """A single-document scalar mapping, with ignored block scalars kept opaque."""
    try:
        decoded = raw.decode("utf-8")
    except UnicodeError:
        raise RoutingError("malformed-metadata") from None
    if any(char in decoded for char in "\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"):
        raise RoutingError("schema-mismatch")
    if "\r" in decoded.replace("\r\n", ""):
        raise RoutingError("schema-mismatch")
    lines = decoded.replace("\r\n", "\n").split("\n")
    metadata, seen = {}, set()
    ignored_block = False
    document_started = False
    document_ended = False
    for line in lines:
        if not line.strip(" \t") or line.lstrip(" \t").startswith("#"):
            continue
        if "\t" in line[:len(line) - len(line.lstrip())]:
            raise RoutingError("schema-mismatch")
        if line.startswith(" "):
            if ignored_block:
                continue
            raise RoutingError("schema-mismatch")
        ignored_block = False
        if line == "---" and not document_started and not document_ended:
            document_started = True
            continue
        if line == "..." and document_started and not document_ended:
            document_ended = True
            continue
        if document_ended:
            raise RoutingError("schema-mismatch")
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*):(?:[ ]+(.*)|[ ]*)", line)
        if not match:
            raise RoutingError("schema-mismatch")
        key, value = match[1], (match[2] or "").strip(" ")
        document_started = True
        if key in seen:
            raise RoutingError("schema-mismatch")
        seen.add(key)
        if value.startswith(("|", ">")):
            if key in COPILOT_FIELDS or not re.fullmatch(r"[|>][+-]?(?: +#.*)?", value):
                raise RoutingError("schema-mismatch")
            ignored_block = True
            continue
        # Unknown keys still need structural validation. In particular an open
        # quote cannot turn its continuation into an allowlisted top-level key.
        if value.startswith('"'):
            try:
                value, end = json.JSONDecoder().raw_decode(value)
                tail = match[2].strip(" ")[end:]
                if tail and not re.fullmatch(r"[ \t]+(?:#.*)?", tail):
                    raise ValueError
            except (ValueError, TypeError):
                raise RoutingError("schema-mismatch") from None
        elif value.startswith("'"):
            quoted = re.fullmatch(r"'((?:[^']|'')*)'(?:[ \t]+#.*)?", value)
            if not quoted:
                raise RoutingError("schema-mismatch")
            value = quoted[1].replace("''", "'")
        else:
            value = re.split(r"[ \t]+#", value, maxsplit=1)[0].rstrip(" \t")
            if value in ("", "null", "Null", "NULL", "~") or value.startswith("#"):
                value = None
            elif (
                value[0] in "[]{},!&*|>%@`"
                or re.search(r":(?:$|[ \t])", value)
                or value[0] in "-?:" and (len(value) == 1 or value[1] in " \t")
            ):
                raise RoutingError("schema-mismatch")
        if key in COPILOT_FIELDS:
            metadata[key] = text(value, optional=True)
    if not metadata:
        raise RoutingError("schema-mismatch")
    return metadata


def _copilot_item(root, session_id, previous, budget, profile_identity=None):
    path = root / "session-state" / session_id / "workspace.yaml"
    info = safe_stat(path, missing_ok=True)
    source_stamp = stamp(info) if info else None
    if info is not None and info.st_size > budget.limits.max_file_bytes:
        raise RoutingError("file-size-bound")
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise RoutingError("not-regular-metadata")
    verified_identity = directory_identity(root) if profile_identity is None else profile_identity
    if (
        previous and previous["pointer_version"] == 2
        and previous["profileIdentity"] == verified_identity
        and previous["nativeSessionId"] == session_id
        and source_stamp is not None and previous["sourceStamp"] == source_stamp
    ):
        return pointer(
            "copilot", root, "copilot-session", session_id,
            profile_identity=verified_identity,
            nativeSessionId=session_id, metadata=dict(previous["metadata"]),
            sourceStamp=source_stamp, availability="metadata",
        ), True
    metadata = _yaml_metadata(read_bytes(path, budget)) if info else {}
    if info is not None and stamp(safe_stat(path)) != source_stamp:
        raise RoutingError("metadata-changed")
    return pointer(
        "copilot", root, "copilot-session", session_id,
        profile_identity=verified_identity,
        nativeSessionId=session_id, metadata=metadata, sourceStamp=source_stamp,
        availability="metadata" if info else "missing-metadata",
    ), False


def _copilot(roots, previous, pending, budget):
    if pending is not None and pending.get("version") == 1:
        pending = None
    if pending is None:
        inventories = []
        for root in roots:
            names, source_stamp = child_directories(root / "session-state", budget)
            inventories.append({
                "profileRoot": str(root), "stamp": source_stamp,
                "profileIdentity": directory_identity(root),
                "names": [name for name in names if UUID.fullmatch(name)],
            })
        pending = {
            "version": 2, "inventories": inventories,
            "profile_index": 0, "offset": 0, "catalog": [],
        }
    validate_pending(pending, roots, budget.limits)
    for inventory in pending["inventories"]:
        if directory_identity(inventory["profileRoot"]) != inventory["profileIdentity"]:
            raise RoutingError("inventory-changed-retry")
        with directory_fd(Path(inventory["profileRoot"]) / "session-state") as fd:
            if stamp(os.fstat(fd)) != inventory["stamp"]:
                raise RoutingError("inventory-changed-retry")
    old = {item["pointer_id"]: item for item in previous}
    # The checkpoint is manager-owned, metadata-only and never an active route.
    pending = {
        **pending, "catalog": list(pending["catalog"]),
        "inventories": pending["inventories"],
    }
    processed = reused = 0
    while pending["profile_index"] < len(roots):
        inventory = pending["inventories"][pending["profile_index"]]
        names = inventory["names"]
        if pending["offset"] == len(names):
            pending["profile_index"] += 1
            pending["offset"] = 0
            continue
        if processed >= budget.limits.batch_size:
            break
        budget.check()
        session_id = names[pending["offset"]]
        root = Path(inventory["profileRoot"])
        key = routing_id("copilot", inventory["profileIdentity"], "copilot-session", session_id)
        item, cached = _copilot_item(root, session_id, old.get(key), budget, inventory["profileIdentity"])
        pending["catalog"].append(item)
        pending["offset"] += 1
        processed += 1
        reused += int(cached)
    complete = pending["profile_index"] == len(roots)
    for inventory in pending["inventories"]:
        if directory_identity(inventory["profileRoot"]) != inventory["profileIdentity"]:
            raise RoutingError("inventory-changed-retry")
        with directory_fd(Path(inventory["profileRoot"]) / "session-state") as fd:
            if stamp(os.fstat(fd)) != inventory["stamp"]:
                raise RoutingError("inventory-changed-retry")
    return {
        "complete": complete,
        "catalog": sorted(pending["catalog"], key=lambda item: item["pointer_id"]) if complete else [],
        "pending": None if complete else pending,
        "observations": [], "examined": processed, "reused": reused,
    }


def validate_pending(pending, roots, limits=None):
    limits = limits or Limits()
    if pending is None:
        return
    if (
        not isinstance(pending, dict)
        or set(pending) != {"version", "inventories", "profile_index", "offset", "catalog"}
        or type(pending["version"]) is not int or pending["version"] not in (1, 2)
        or not isinstance(pending["inventories"], list)
        or len(pending["inventories"]) != len(roots)
        or not isinstance(pending["catalog"], list)
        or len(pending["catalog"]) > limits.max_entries
        or type(pending["profile_index"]) is not int
        or not 0 <= pending["profile_index"] <= len(roots)
        or type(pending["offset"]) is not int or pending["offset"] < 0
        or pending["profile_index"] == len(roots) and pending["offset"] != 0
    ):
        raise RoutingError("checkpoint-schema-mismatch")
    count = 0
    expected = []
    for index, inventory in enumerate(pending["inventories"]):
        if (
            not isinstance(inventory, dict)
            or set(inventory) != (
                {"profileRoot", "stamp", "names"} | ({"profileIdentity"} if pending["version"] == 2 else set())
            )
            or inventory["profileRoot"] != str(roots[index])
            or not isinstance(inventory["stamp"], list) or len(inventory["stamp"]) != 5
            or any(type(n) is not int or n < 0 for n in inventory["stamp"])
            or not isinstance(inventory["names"], list)
        ):
            raise RoutingError("checkpoint-schema-mismatch")
        if pending["version"] == 2:
            validate_filesystem_identity(inventory["profileIdentity"])
        names = inventory["names"]
        if any(not isinstance(name, str) or not UUID.fullmatch(name) for name in names):
            raise RoutingError("checkpoint-schema-mismatch")
        if names != sorted(set(names)):
            raise RoutingError("checkpoint-schema-mismatch")
        count += len(names)
        stop = len(names) if index < pending["profile_index"] else (
            pending["offset"] if index == pending["profile_index"] else 0
        )
        if stop > len(names):
            raise RoutingError("checkpoint-schema-mismatch")
        expected.extend((str(roots[index]), name) for name in names[:stop])
    if count > limits.max_entries:
        raise RoutingError("count-bound")
    if len(expected) != len(pending["catalog"]):
        raise RoutingError("checkpoint-schema-mismatch")
    for item, (root, session_id) in zip(pending["catalog"], expected):
        validate_pointer(item)
        if item["provider"] != "copilot" or item["profileRoot"] != root or item["nativeSessionId"] != session_id:
            raise RoutingError("checkpoint-schema-mismatch")
        if item["pointer_version"] != pending["version"]:
            raise RoutingError("checkpoint-schema-mismatch")
        if pending["version"] == 2:
            inventory = next(value for value in pending["inventories"] if value["profileRoot"] == root)
            if item["profileIdentity"] != inventory["profileIdentity"]:
                raise RoutingError("checkpoint-schema-mismatch")


def _claude(roots, budget):
    catalog = []
    for root in roots:
        profile_identity = directory_identity(root)
        native_root = root / "projects"
        names, source_stamp = child_directories(native_root, budget)
        for name in names:
            budget.check()
            native_key(name)
            path = native_root / name / "sessions-index.json"
            info = safe_stat(path, missing_ok=True)
            original, associations, version = None, [], None
            if info is not None:
                data = read_json(path, budget)
                if (
                    not isinstance(data, dict) or type(data.get("version")) is not int
                    or data["version"] != 1 or not isinstance(data.get("entries"), list)
                ):
                    raise RoutingError("schema-mismatch")
                version = data["version"]
                original = text(data.get("originalPath"), optional=True)
                pairs = set()
                for entry in data["entries"]:
                    budget.entry()
                    if not isinstance(entry, dict):
                        raise RoutingError("schema-mismatch")
                    pair = (
                        text(entry.get("originalPath", original), optional=True),
                        text(entry.get("projectPath"), optional=True),
                    )
                    if pair != (None, None):
                        pairs.add(pair)
                associations = [
                    {"originalPath": origin, "projectPath": project}
                    for origin, project in sorted(pairs, key=lambda pair: (pair[0] or "", pair[1] or ""))
                ]
            catalog.append(pointer(
                "claude", root, "claude-project", name, nativeRoot=str(native_root),
                profile_identity=profile_identity,
                nativeKey=name, indexVersion=version, originalPath=original,
                pathAssociations=associations, availability="indexed" if info else "missing-index",
            ))
        with directory_fd(native_root) as fd:
            if stamp(os.fstat(fd)) != source_stamp:
                raise RoutingError("metadata-changed")
        if directory_identity(root) != profile_identity:
            raise RoutingError("metadata-changed")
    return catalog


def _sqlite_sidecars(path):
    # Never let SQLite open a native WAL/SHM, create one, or silently ignore a WAL.
    for suffix in ("-wal", "-journal", "-shm"):
        info = safe_stat(str(path) + suffix, missing_ok=True)
        if info is not None:
            if not stat.S_ISREG(info.st_mode):
                raise RoutingError("not-regular-metadata")
            if info.st_size and suffix != "-shm":
                raise RoutingError("native-wal-active" if suffix == "-wal" else "native-busy")


def _hermes_database(root, budget):
    try:
        import fcntl
    except ImportError:
        raise RoutingError("sqlite-readonly-unavailable") from None
    path = root / "state.db"
    profile_identity = directory_identity(root)
    _sqlite_sidecars(path)
    catalog = []
    with regular_fd(path) as fd:
        before = stamp(os.fstat(fd))
        if before[2] > 2 * 1024 ** 3:
            raise RoutingError("database-size-bound")
        try:
            # A shared lock over SQLite's lock bytes refuses a rollback writer.
            fcntl.lockf(fd, fcntl.LOCK_SH | fcntl.LOCK_NB, 512, 0x40000000, os.SEEK_SET)
        except OSError:
            raise RoutingError("native-busy") from None
        _sqlite_sidecars(path)
        connection = None
        try:
            # The OS-owned fd alias pins the already no-follow-opened inode.
            # immutable mode guarantees SQLite cannot write even to native SHM.
            connection = sqlite3.connect(
                f"file:/dev/fd/{fd}?mode=ro&immutable=1", uri=True, timeout=0
            )
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA trusted_schema=OFF")
            if hasattr(connection, "setlimit"):
                connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, budget.limits.max_file_bytes)
            connection.set_progress_handler(
                lambda: int(budget.clock() >= budget.deadline), 100
            )
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != 0:
                raise RoutingError("schema-mismatch")
            tables = {}
            for table in HERMES_TABLES:
                rows = connection.execute(
                    "SELECT type FROM pragma_table_list WHERE schema = 'main' AND name = ?",
                    (table,),
                ).fetchall()
                if not rows:
                    continue
                if rows != [("table",)]:
                    raise RoutingError("schema-mismatch")
                columns = {
                    row[0]: row[1].upper()
                    for row in connection.execute(
                        "SELECT name, type FROM pragma_table_info(?)", (table,)
                    )
                }
                if "id" not in columns or columns["id"] not in ("TEXT", "INTEGER"):
                    raise RoutingError("schema-mismatch")
                tables[table] = sorted(HERMES_TABLES[table][1] & columns.keys())
            if not tables:
                raise RoutingError("schema-mismatch")

            def authorize(action, arg1, arg2, database, trigger):
                if action == sqlite3.SQLITE_SELECT:
                    return sqlite3.SQLITE_OK
                if (
                    action == sqlite3.SQLITE_READ and database == "main"
                    and arg1 in tables and arg2 in tables[arg1] and trigger is None
                ):
                    return sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_FUNCTION and arg2 in ("typeof", "substr"):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            connection.set_authorizer(authorize)
            for table, columns in tables.items():
                selection = ", ".join(
                    f'CASE WHEN typeof("{column}") IN (\'text\', \'blob\') '
                    f'THEN substr("{column}", 1, 4097) ELSE "{column}" END'
                    for column in columns
                )
                rows = connection.execute(
                    f'SELECT {selection} FROM "{table}" LIMIT ?',
                    (budget.limits.max_entries + 1,),
                )
                seen = set()
                for row in rows:
                    budget.entry()
                    metadata = {column: scalar(value) for column, value in zip(columns, row)}
                    identity = metadata["id"]
                    if type(identity) not in (str, int) or identity in seen:
                        raise RoutingError("schema-mismatch")
                    seen.add(identity)
                    budget.consume(len(json.dumps(metadata).encode("utf-8")))
                    catalog.append(pointer(
                        "hermes", root, HERMES_TABLES[table][0], [table, identity],
                        profile_identity=profile_identity,
                        nativeTable=table, nativeId=identity, schemaVersion=version,
                        metadata=metadata,
                    ))
            budget.check()
            _sqlite_sidecars(path)
            if stamp(os.fstat(fd)) != before or stamp(safe_stat(path)) != before:
                raise RoutingError("metadata-changed")
            if directory_identity(root) != profile_identity:
                raise RoutingError("metadata-changed")
        except sqlite3.Error:
            budget.check()
            raise RoutingError("sqlite-busy-or-schema-mismatch") from None
        finally:
            if connection is not None:
                connection.close()
    return catalog


def _scout(roots, budget):
    catalog = []
    for root in roots:
        profile_identity = directory_identity(root)
        data = read_json(root / "m-sessions" / "workspaces.json", budget)
        if (
            not isinstance(data, dict) or type(data.get("version")) is not int
            or data["version"] != 3 or not isinstance(data.get("workspaces"), list)
        ):
            raise RoutingError("schema-mismatch")
        for entry in data["workspaces"]:
            budget.entry()
            if not isinstance(entry, dict):
                raise RoutingError("schema-mismatch")
            workspace_id = text(entry.get("id"))
            catalog.append(pointer(
                "scout", root, "scout-workspace", workspace_id,
                profile_identity=profile_identity,
                nativeVersion=3, workspaceId=workspace_id,
                providerId=text(entry.get("providerId")), rootId=text(entry.get("rootId")),
            ))
        if directory_identity(root) != profile_identity:
            raise RoutingError("metadata-changed")
    return catalog


def scan_provider(provider, profile_roots, *, previous=(), pending=None, limits=None):
    """Inspect explicit roots only; callers alone own staging/selection/registry writes."""
    if provider not in PROVIDERS:
        raise RoutingError("unknown-provider")
    if not profile_roots or len(profile_roots) > 16:
        raise RoutingError("profile-count-bound")
    budget = Budget(limits)
    roots = sorted({absolute_path(root) for root in profile_roots}, key=str)
    home_ancestors = directory_info(Path.home(), missing_ok=True)["ancestors"]
    for root in roots:
        budget.check()
        if directory_identity(root) in home_ancestors:
            raise RoutingError("broad-native-root-refused")
        with directory_fd(root):
            pass
    roots = unique_directories(roots)
    profile_identities = {str(root): directory_identity(root) for root in roots}
    for item in previous:
        validate_pointer(item)
        if item["provider"] != provider:
            raise RoutingError("provider-partition-mismatch")
    if provider == "copilot":
        result = _copilot(roots, previous, pending, budget)
    else:
        observations = []
        if provider == "claude":
            catalog = _claude(roots, budget)
        elif provider == "hermes":
            catalog = []
            for root in roots:
                catalog.extend(_hermes_database(root, budget))
        elif provider == "scout":
            catalog = _scout(roots, budget)
        else:
            catalog = []
            if any(root.name.casefold() not in ("grokbot.app", ".grokbot", "grokbot") for root in roots):
                raise RoutingError("grokbot-root-unrecognized")
            observations = [
                {
                    "provider": "grokbot", "profileRoot": str(root),
                    "state": "app-detected", "mapping": "workspace-mapping-unavailable",
                    "observation_id": grokbot_observation_id(root, profile_identity=profile_identities[str(root)]),
                    "observation_version": 2, "profileIdentity": profile_identities[str(root)],
                }
                for root in roots
            ]
        result = {
            "complete": True, "catalog": sorted(catalog, key=lambda item: item["pointer_id"]),
            "observations": observations, "pending": None, "reused": 0,
            "examined": len(catalog),
        }
    keys = [item["pointer_id"] for item in result["catalog"]]
    if len(keys) != len(set(keys)):
        raise RoutingError("duplicate-native-identity")
    candidates = result["catalog"] if result["complete"] else result["pending"]["catalog"]
    size = 0
    for item in candidates:
        budget.check()
        if item["profileIdentity"] != profile_identities.get(item["profileRoot"]):
            raise RoutingError("metadata-changed")
        size += len(json.dumps(item, separators=(",", ":")).encode("utf-8"))
        if size > MAX_CATALOG_BYTES:
            raise RoutingError("catalog-size-bound")
    budget.check()
    for root in roots:
        if directory_identity(root) != profile_identities[str(root)]:
            raise RoutingError("metadata-changed")
    result.update(provider=provider, profileRoots=list(map(str, roots)))
    result["profileIdentities"] = profile_identities
    return result
