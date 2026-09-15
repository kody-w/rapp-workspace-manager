"""Exact public Grail dependency images; no discovery, plugins, or import-path fallback."""

import base64
import builtins
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

from routing_io import (
    RoutingError, directory_fd, directory_identity, read_bytes, unique_object,
    reject_constant,
)

PROFILE = "rapp-workspace/grail-1.0"
BRAND = "RAPP Workspace/1 Grail"
PROTOCOL = "protocols/rapp-workspace/grail-1.0"
SPEC_SHA256 = "3da45fabcfedb94c67a032ebb12fc02716b44b32822933d43c998825c632935f"
MANIFEST_SHA256 = "fa4bee666cc56c1db43d9f5f452358f8d623e85deb31b8fcb32b58553cebbdae"
PARENT_COMMIT = "dda32d741c7218f41443a5bd17eebfe0eae82cb7"
GUARANTEES = (
    "rapp_integrity", "observation", "semantic_fidelity",
    "current_authorization", "safe_deployment",
)
MODULES = ("schema_source", "common", "pins", "safe_kernel")
STDLIB = frozenset({
    "_strptime", "argparse", "base64", "contextlib", "dataclasses", "datetime", "fcntl",
    "hashlib", "hmac", "io", "json", "os", "pathlib", "re", "sqlite3", "stat", "subprocess",
    "types", "unicodedata", "urllib.parse", "uuid", "zipfile",
})
MAX_IMAGE = 4 * 1024 * 1024


def require(condition, code):
    if not condition:
        raise RoutingError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def measurement(value):
    """Manager file/state checksum, not a RAPP identity or a protocol primitive."""
    return sha(encode(value))


def parse(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise RoutingError("grail-invalid-json") from None


def explicit_path(value):
    require(isinstance(value, (str, os.PathLike)), "grail-explicit-absolute-path-required")
    value = os.fspath(value)
    require(isinstance(value, str) and 0 < len(value) <= 4096
            and not any(ord(c) < 32 for c in value), "grail-invalid-path")
    path = Path(value)
    require(path.is_absolute() and ".." not in path.parts and len(path.parts) <= 128
            and not value.startswith("//"), "grail-explicit-absolute-path-required")
    return path


def relative_name(value):
    require(type(value) is str and 0 < len(value) <= 256, "grail-closure-path")
    path = Path(value)
    require(not path.is_absolute() and ".." not in path.parts
            and str(path) == value, "grail-closure-path")
    return value


def stable_read(path, limit=MAX_IMAGE):
    """Verify the named object as well as the descriptor used by the manager reader."""
    with directory_fd(Path(path).parent) as fd:
        before = os.stat(Path(path).name, dir_fd=fd, follow_symlinks=False)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "grail-unsafe-file")
        raw = read_bytes(path, max_bytes=limit)
        after = os.stat(Path(path).name, dir_fd=fd, follow_symlinks=False)
        fields = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
                            s.st_mtime_ns, s.st_ctime_ns)
        require(fields(before) == fields(after), "grail-named-file-changed")
        return raw


def manifest_entries(manifest):
    require(manifest.get("profile") == PROFILE and manifest.get("parent") == "rapp/1"
            and manifest.get("authority") is False, "grail-wrong-protocol")
    result = {}
    for section in ("normative", "reference"):
        for row in manifest[section]:
            result[PROTOCOL + "/" + relative_name(row["path"])] = row
    for row in manifest["repository_evidence"]:
        result[relative_name(row["path"])] = row
    row = manifest["provenance"]
    result[PROTOCOL + "/" + relative_name(row["path"])] = row
    row = manifest["historical_catalog"]
    result[relative_name(row["path"])] = row
    return result


def verify_image(files):
    require(type(files) is dict and len(files) <= 64, "grail-closure-bound")
    raw = files.get(PROTOCOL + "/manifest.json")
    require(type(raw) is bytes and sha(raw) == MANIFEST_SHA256, "grail-manifest-pin-mismatch")
    manifest = parse(raw)
    entries = manifest_entries(manifest)
    require(set(files) == set(entries) | {PROTOCOL + "/manifest.json", "protocols/index.json"},
            "grail-executable-closure-mismatch")
    require(sum(len(raw) for raw in files.values()) <= MAX_IMAGE, "grail-closure-bound")
    for name, entry in entries.items():
        value = files[name]
        require(type(value) is bytes and len(value) == entry["bytes"]
                and sha(value) == entry["sha256"], "grail-closure-pin-mismatch")
    require(sha(files[PROTOCOL + "/SPEC.md"]) == SPEC_SHA256, "grail-spec-pin-mismatch")
    index = parse(files["protocols/index.json"])
    selected = [p for p in index["profiles"] if p["name"].startswith("rapp-workspace/")]
    require(index.get("workspace_latest") == PROFILE and len(selected) == 1
            and selected[0]["name"] == PROFILE
            and selected[0]["spec_sha256"] == SPEC_SHA256
            and selected[0]["manifest_sha256"] == MANIFEST_SHA256,
            "grail-index-pin-mismatch")
    return manifest


def capture_checkout(checkout):
    checkout = explicit_path(checkout)
    identity = directory_identity(checkout)
    raw = stable_read(checkout / PROTOCOL / "manifest.json")
    require(sha(raw) == MANIFEST_SHA256, "grail-manifest-pin-mismatch")
    files = {PROTOCOL + "/manifest.json": raw}
    for name in manifest_entries(parse(raw)):
        files[name] = stable_read(checkout / name)
    files["protocols/index.json"] = stable_read(checkout / "protocols/index.json")
    for directory, suffix in (("reference", ".py"), ("schemas", ".json")):
        expected = {Path(name).name for name in files
                    if name.startswith(PROTOCOL + "/" + directory + "/")}
        with directory_fd(checkout / PROTOCOL / directory) as fd:
            names = set()
            with os.scandir(fd) as rows:
                for number, row in enumerate(rows):
                    require(number < 64, "grail-closure-bound")
                    if row.name.endswith(suffix):
                        require(row.is_file(follow_symlinks=False), "grail-unsafe-runtime-file")
                        names.add(row.name)
            require(names == expected, "grail-executable-closure-mismatch")
    verify_image(files)
    require(identity == directory_identity(checkout), "grail-checkout-identity-changed")
    return files


def image_json(files):
    verify_image(files)
    return {"schema": "rapp-workspace-manager/grail-image/1", "spec_id": PROFILE,
            "files": {name: base64.b64encode(raw).decode("ascii") for name, raw in sorted(files.items())}}


def read_image(raw):
    data = parse(raw)
    require(type(data) is dict and set(data) == {"schema", "spec_id", "files"}
            and data["schema"] == "rapp-workspace-manager/grail-image/1"
            and data["spec_id"] == PROFILE and type(data["files"]) is dict,
            "grail-image-schema")
    try:
        files = {relative_name(name): base64.b64decode(value, validate=True)
                 for name, value in data["files"].items()}
    except (TypeError, ValueError):
        raise RoutingError("grail-image-encoding") from None
    verify_image(files)
    return files


class Runtime:
    """Compile only captured, pinned modules; never import from a checkout or its bytecode."""

    def __init__(self, checkout, rapp1_path, files, *, historical=False):
        self.checkout, self.rapp1_path = explicit_path(checkout), explicit_path(rapp1_path)
        self.files, self.manifest = files, verify_image(files)
        self.modules = {}
        package = "_manager_grail_" + MANIFEST_SHA256[:12] + "_" + str(id(self))
        trusted_import = builtins.__import__

        def importer(name, globals=None, locals=None, fromlist=(), level=0):
            require(level == 0, "grail-relative-import-disabled")
            if name in MODULES:
                require(name in self.modules, "grail-runtime-import-order")
                return self.modules[name]
            require(name in STDLIB, "grail-ambient-import-disabled")
            return trusted_import(name, globals, locals, fromlist, level)

        try:
            for name in MODULES:
                module = types.ModuleType(package + "." + name)
                module.__file__ = str(self.checkout / PROTOCOL / "reference" / (name + ".py"))
                module.__builtins__ = {**vars(builtins), "__import__": importer}
                self.modules[name] = module
                sys.modules[module.__name__] = module
                raw = files[PROTOCOL + "/reference/" + name + ".py"]
                exec(compile(raw, module.__file__, "exec"), module.__dict__)
            self.common, self.kernel = self.modules["common"], self.modules["safe_kernel"]
            self.common.ROOT = self.checkout / PROTOCOL
            live_read = self.common.read_file

            def captured_read(path, limit=self.common.MAX_BYTES):
                path = Path(path).absolute()
                if path.is_relative_to(self.checkout):
                    name = str(path.relative_to(self.checkout))
                    if name in self.files:
                        value = self.files[name]
                        require(len(value) <= limit, "grail-validator-byte-bound")
                        return value
                    require(path.is_relative_to(self.rapp1_path), "grail-unpinned-validator-input")
                return live_read(path, limit)

            parent_schema = self.common.SchemaSet
            documents = {Path(name).name: parse(value) for name, value in files.items()
                         if name.startswith(PROTOCOL + "/schemas/")}

            class CapturedSchemas(parent_schema):
                def __init__(self, parent):
                    self.parent, self.documents = parent, documents

            # Parent provenance and validator schemas consume the captured image too.
            # Fresh kernel qualification still re-reads the live closure after construction.
            self.common.read_file = captured_read
            self.common.SchemaSet = CapturedSchemas
            index = parse(files["protocols/index.json"])
            selected = [p for p in index["profiles"] if p["name"].startswith("rapp-workspace/")]
            require(selected == [self.modules["pins"].index_profile()]
                    and index.get("authority") is False and index.get("workspace_brand") == BRAND,
                    "grail-exact-index-profile-mismatch")
            self.core = self.common.Parent(self.rapp1_path)
            require(self.core.pin["commit"] == PARENT_COMMIT, "grail-parent-pin-mismatch")
            if not historical:
                self.common.read_file = live_read
        except BaseException:
            self.close()
            raise

    def close(self):
        for module in self.modules.values():
            sys.modules.pop(module.__name__, None)


def contract():
    return {"spec_id": PROFILE, "brand": BRAND, "spec_sha256": SPEC_SHA256,
            "manifest_sha256": MANIFEST_SHA256, "parent_commit": PARENT_COMMIT,
            "authority": False, "external_effects": "disabled"}
