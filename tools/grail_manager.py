"""Frame Anything local control plane. Graphs, receipts and views never grant authority."""

import base64
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

import grail_runtime as runtime
from grail_runtime import (
    BRAND, GUARANTEES, MANIFEST_SHA256, PROFILE, SPEC_SHA256, encode, explicit_path,
    measurement, parse, require, sha, stable_read,
)
from routing_io import (
    RoutingError, atomic_text, directory_fd, directory_identity, directory_info, manager_lock,
    safe_stat, validate_filesystem_identity,
)

STATE_SCHEMA = "rapp-workspace-manager/grail-state/1"
RIGHTS = ("capture", "retention", "local_synthesis", "adoption", "materialization")
FORMS = ("supplied-octets", "file-octets", "directory-metadata-fixture", "registry-metadata")
MAX_JOBS = 32
MAX_STATE = 1024 * 1024
SLUG = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
UNSAFE_COMPONENTS = frozenset({
    ".ssh", ".aws", ".azure", ".config", ".git", ".gnupg", ".kube", ".npmrc",
    ".pypirc", ".netrc", ".copilot", ".claude", ".hermes", ".scout", ".grokbot",
    ".grok", "credentials", "credential", "secrets", "keychain", "keychains",
    "application support", "cookies", "login data", "sessions",
})
STATE_FIELDS = {
    "schema", "version", "spec_id", "manager_rappid", "world_id", "binding_sha256",
    "seed_lineage", "adopted_projection_head", "frontier", "manager_frontier",
    "jobs", "stages", "projections", "checkpoint",
}
JOB_FIELDS = {
    "id", "subject", "form", "source", "observations", "attempts", "receipts",
    "outcome", "reason", "plan", "feedback", "migration", "capture_frontier",
}
MANAGER_FRONTIER = {
    "registry_sha256", "identity_sha256", "routing_sha256", "suppression_sha256",
    "organization_sha256", "worlds_sha256", "policy_sha256", "binding_sha256",
}
PROTOCOL_FRONTIER = {
    "instance_rappid", "world_id", "policy", "graph_head", "adoption_head",
    "routing_head", "suppressions", "source_bindings", "runtime_sha256", "sequence",
}
STAGE_FIELDS = {
    "job", "request", "protocol_frontier", "manager_frontier", "token", "contract",
    "status", "record",
}
BINDING_FIELDS = {
    "schema", "version", "protocol", "checkout", "checkout_identity", "rapp1_path",
    "rapp1_identity", "image_sha256", "closure", "manager_rappid", "world_id",
}
POLICY_FIELDS = {
    "schema", "version", "spec_id", "manager_rappid", "world_id", "sequence",
    "expires_utc", "rights", "scopes", "max_attempts", "max_depth", "max_frames",
    "max_total_octets",
}


def manager():
    import workspace_manager
    return workspace_manager


def clock():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def closed(value, keys):
    require(type(value) is dict and set(value) == set(keys), "grail-closed-state-schema")


def slug(value):
    require(type(value) is str and SLUG.fullmatch(value) is not None, "grail-invalid-local-job-id")
    return value


def digest(value):
    require(type(value) is str and HASH.fullmatch(value) is not None, "grail-invalid-checksum")


def address(value, *, optional=False, particle=False):
    if optional and value is None:
        return
    closed(value, {"space", "hash"})
    require(value["space"] == ("rapp/1:particle" if particle else "rapp/1:wave"),
            "grail-address-kind")
    digest(value["hash"])


def subject(value):
    closed(value, {"namespace", "native_key"})
    for text in value.values():
        require(type(text) is str and 0 < len(text) <= 128 and text.isascii()
                and all(32 <= ord(c) < 127 for c in text), "grail-invalid-explicit-subject")
    return value


def protocol_frontier(value):
    closed(value, PROTOCOL_FRONTIER)
    require(type(value["sequence"]) is int and 0 <= value["sequence"] <= 100000,
            "grail-invalid-frontier")
    for key in ("policy", "suppressions", "source_bindings"):
        address(value[key], particle=True)
    for key in ("graph_head", "adoption_head", "routing_head"):
        address(value[key], optional=True)
    require(value["runtime_sha256"] == MANIFEST_SHA256, "grail-wrong-runtime-frontier")
    for key in ("instance_rappid", "world_id"):
        require(type(value[key]) is str and bool(value[key]), "grail-invalid-frontier")


def manager_frontier(value):
    closed(value, MANAGER_FRONTIER)
    for item in value.values():
        digest(item)


def validate_state(value):
    closed(value, STATE_FIELDS)
    require(value["schema"] == STATE_SCHEMA and type(value["version"]) is int
            and value["version"] == 1 and value["spec_id"] == PROFILE, "grail-state-version")
    for key in ("manager_rappid", "world_id"):
        require(type(value[key]) is str and 0 < len(value[key]) <= 4096, "grail-state-identity")
    digest(value["binding_sha256"])
    require(type(value["seed_lineage"]) is list and len(value["seed_lineage"]) == 1,
            "grail-single-seed-lineage")
    address(value["seed_lineage"][0])
    address(value["adopted_projection_head"], optional=True)
    protocol_frontier(value["frontier"])
    manager_frontier(value["manager_frontier"])
    require(type(value["jobs"]) is dict and len(value["jobs"]) <= MAX_JOBS, "grail-job-bound")
    for name, job in value["jobs"].items():
        slug(name)
        closed(job, JOB_FIELDS)
        require(job["id"] == name and job["form"] in FORMS, "grail-job-schema")
        subject(job["subject"])
        address(job["source"])
        require(type(job["observations"]) is list and 1 <= len(job["observations"]) <= 2,
                "grail-observation-bound")
        for ref in job["observations"]:
            address(ref)
        require(type(job["attempts"]) is list and len(job["attempts"]) <= 128, "grail-attempt-bound")
        for attempt in job["attempts"]:
            closed(attempt, {"lens", "result", "kind", "reason"})
            address(attempt["lens"], optional=True)
            address(attempt["result"])
            require(attempt["kind"] in ("candidate", "refused", "stopped")
                    and (attempt["reason"] is None or type(attempt["reason"]) is str),
                    "grail-attempt-schema")
        closed(job["receipts"], GUARANTEES)
        for ref in job["receipts"].values():
            address(ref)
        require(job["outcome"] in ("captured", "candidate", "refused", "stopped", "staged", "adopted")
                and (job["reason"] is None or type(job["reason"]) is str), "grail-outcome-schema")
        if job["plan"] is not None:
            closed(job["plan"], {"strategy", "field"})
            require(job["plan"]["strategy"] in ("identity", "adaptive", "strict-field")
                    and type(job["plan"]["field"]) is str
                    and len(job["plan"]["field"]) <= 128, "grail-plan-schema")
        if job["feedback"] is not None:
            closed(job["feedback"], {"refusal", "exhaust", "source"})
            for ref in job["feedback"].values():
                address(ref)
        if job["migration"] is not None:
            migration = job["migration"]
            closed(migration, {"registry_sha256", "unresolved", "worlds", "behavior_coverage", "routes_changed"})
            digest(migration["registry_sha256"])
            require(type(migration["unresolved"]) is list and len(migration["unresolved"]) <= 10000
                    and all(type(item) is str for item in migration["unresolved"])
                    and type(migration["worlds"]) is list
                    and all(item is None or type(item) is str for item in migration["worlds"])
                    and migration["behavior_coverage"] == "registry-metadata-only"
                    and migration["routes_changed"] is False, "grail-migration-schema")
        manager_frontier(job["capture_frontier"])
    require(type(value["stages"]) is dict and len(value["stages"]) <= MAX_JOBS, "grail-stage-bound")
    for operation, stage in value["stages"].items():
        slug(operation)
        closed(stage, STAGE_FIELDS)
        require(type(stage["job"]) is str and stage["job"] in value["jobs"]
                and stage["status"] in ("staged", "adopted"),
                "grail-stage-schema")
        address(stage["request"])
        address(stage["record"], optional=True)
        require((stage["status"] == "adopted") == (stage["record"] is not None), "grail-stage-schema")
        protocol_frontier(stage["protocol_frontier"])
        manager_frontier(stage["manager_frontier"])
        digest(stage["token"])
        require(stage["contract"] == identity_contract(), "grail-contract-schema")
    projection = value["projections"]
    closed(projection, {"generation", "focus", "files", "authority", "native_routes"})
    require(type(projection["generation"]) is int and projection["generation"] >= 0
            and (projection["focus"] is None or
                 type(projection["focus"]) is str and projection["focus"] in value["jobs"])
            and projection["authority"] is False and projection["native_routes"] is False,
            "grail-projection-schema")
    require(type(projection["files"]) is list and len(projection["files"]) <= 3, "grail-projection-schema")
    for file in projection["files"]:
        closed(file, {"name", "sha256", "bytes"})
        require(file["name"] in ("view.json", "view.md", "estate.code-workspace")
                and type(file["bytes"]) is int and file["bytes"] >= 0, "grail-projection-schema")
        digest(file["sha256"])
    check = value["checkpoint"]
    closed(check, {"instance_rappid", "world_id", "frames", "frontier", "faults", "suppressions", "adoptions"})
    require(check["instance_rappid"] == value["manager_rappid"] and check["world_id"] == value["world_id"],
            "grail-checkpoint-identity")
    protocol_frontier(check["frontier"])
    require(type(check["frames"]) is list and len(check["frames"]) <= 512, "grail-checkpoint-bound")
    for frame in check["frames"]:
        closed(frame, {"seq", "hash"})
        require(type(frame["seq"]) is int and 0 <= frame["seq"] < 512, "grail-checkpoint-frame")
        digest(frame["hash"])
    for key in ("faults", "suppressions"):
        require(type(check[key]) is list and len(check[key]) <= 512, "grail-checkpoint-bound")
        for item in check[key]:
            digest(item)
    require(type(check["adoptions"]) is list and len(check["adoptions"]) <= MAX_JOBS,
            "grail-checkpoint-bound")
    for item in check["adoptions"]:
        require(type(item) is list and len(item) == 4, "grail-checkpoint-adoption")
        slug(item[0])
        for item_hash in item[1:]:
            digest(item_hash)
    require(len(encode(value)) <= MAX_STATE, "grail-state-byte-bound")
    return value


def identity_contract():
    return {"operation": "identity-octets", "field": "",
            "coverage": "complete-captured-octets", "inverse": True}


def private_directory(path, *, create=False):
    with directory_fd(path, create=create) as fd:
        info = os.fstat(fd)
        require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
                "grail-controller-directory-must-be-private")


def owned_file(path, *, missing=False, limit=MAX_STATE):
    info = safe_stat(path, missing_ok=missing)
    if info is None:
        return None
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_mode & 0o077 == 0 and info.st_nlink == 1, "grail-unsafe-owned-file")
    return stable_read(path, limit)


def write_json(path, value):
    atomic_text(path, encode(value).decode("ascii"))


def identity_and_registry(workspace):
    wm = manager()
    identity = wm.manager_identity(workspace)
    registry = wm.load_registry(workspace)
    guard = stable_read(Path(workspace) / "README.md", 65536)
    require(b"PRIVATE / NEVER PUBLISH" in guard, "grail-private-manager-guard-required")
    require(safe_stat(Path(workspace) / "frames", missing_ok=True) is None,
            "grail-existing-manager-root-stream-needs-qualified-transition")
    return identity, registry


def binding_document(workspace):
    private_directory(Path(workspace) / ".grail")
    raw = owned_file(Path(workspace) / ".grail/binding.json")
    value = parse(raw)
    closed(value, BINDING_FIELDS)
    require(value["schema"] == "rapp-workspace-manager/grail-binding/1"
            and type(value["version"]) is int and value["version"] == 1
            and value["protocol"] == runtime.contract(), "grail-binding-version")
    for key in ("checkout", "rapp1_path"):
        explicit_path(value[key])
    for key in ("checkout_identity", "rapp1_identity"):
        validate_filesystem_identity(value[key])
    digest(value["image_sha256"])
    require(type(value["closure"]) is list and len(value["closure"]) <= 64, "grail-binding-closure")
    for entry in value["closure"]:
        closed(entry, {"path", "sha256", "bytes"})
        runtime.relative_name(entry["path"])
        digest(entry["sha256"])
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= runtime.MAX_IMAGE,
                "grail-binding-closure")
    return value, raw


def closure_records(files):
    return [{"path": name, "sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())]


def bind(workspace, checkout, rapp1_path):
    workspace = explicit_path(workspace)
    checkout, rapp1_path = explicit_path(checkout), explicit_path(rapp1_path)
    with manager_lock(workspace):
        identity, _ = identity_and_registry(workspace)
        files = runtime.capture_checkout(checkout)
        image = runtime.image_json(files)
        image_raw = encode(image)
        image_runtime = runtime.Runtime(checkout, rapp1_path, files)
        try:
            require(image_runtime.core.r.rappid_valid(identity["rappid"]), "grail-invalid-manager-rappid")
        finally:
            image_runtime.close()
        binding = {
            "schema": "rapp-workspace-manager/grail-binding/1", "version": 1,
            "protocol": runtime.contract(), "checkout": str(checkout),
            "checkout_identity": directory_identity(checkout), "rapp1_path": str(rapp1_path),
            "rapp1_identity": directory_identity(rapp1_path), "image_sha256": sha(image_raw),
            "closure": closure_records(files), "manager_rappid": identity["rappid"],
            "world_id": identity["world_id"],
        }
        path = workspace / ".grail"
        private_directory(path, create=True)
        old = owned_file(path / "binding.json", missing=True)
        require(old is None or old == encode(binding), "grail-existing-binding-does-not-remint-or-rebind")
        retained = owned_file(path / "runtime-image.json", missing=True, limit=runtime.MAX_IMAGE * 2)
        require(retained is None or retained == image_raw, "grail-existing-runtime-image-conflict")
        if retained is None:
            write_json(path / "runtime-image.json", image)
        if old is None:
            write_json(path / "binding.json", binding)
        return {**runtime.contract(), "bound": True, "identity_preserved": True,
                "closure_files": len(files), "binding_sha256": sha(encode(binding))}


def load_runtime(workspace, *, historical=False):
    binding, raw = binding_document(workspace)
    identity, _ = identity_and_registry(workspace)
    require(binding["manager_rappid"] == identity["rappid"] and binding["world_id"] == identity["world_id"],
            "grail-manager-identity-or-world-changed")
    retained = owned_file(Path(workspace) / ".grail/runtime-image.json", limit=runtime.MAX_IMAGE * 2)
    require(sha(retained) == binding["image_sha256"], "grail-runtime-image-substitution")
    files = runtime.read_image(retained)
    require(closure_records(files) == binding["closure"], "grail-runtime-closure-substitution")
    require(directory_identity(binding["rapp1_path"]) == binding["rapp1_identity"],
            "grail-parent-checkout-rebinding-refused")
    if not historical:
        require(directory_identity(binding["checkout"]) == binding["checkout_identity"],
                "grail-protocol-checkout-rebinding-refused")
        require(runtime.capture_checkout(binding["checkout"]) == files, "grail-current-runtime-drift")
    return runtime.Runtime(binding["checkout"], binding["rapp1_path"], files, historical=historical), binding, sha(raw)


def validate_policy(value):
    closed(value, POLICY_FIELDS)
    require(value["schema"] == "rapp-workspace-manager/grail-policy/1"
            and type(value["version"]) is int and value["version"] == 1
            and value["spec_id"] == PROFILE and type(value["sequence"]) is int
            and value["sequence"] >= 1, "grail-policy-version")
    require(type(value["rights"]) is list and all(type(right) is str for right in value["rights"])
            and value["rights"] == sorted(set(value["rights"]))
            and set(value["rights"]) <= set(RIGHTS), "grail-policy-rights")
    require(type(value["scopes"]) is list and 2 <= len(value["scopes"]) <= MAX_JOBS + 2,
            "grail-scope-bound")
    subjects = set()
    for scope in value["scopes"]:
        closed(scope, {"subject", "form", "path"})
        subject(scope["subject"])
        key = encode(scope["subject"])
        require(key not in subjects and scope["form"] in FORMS + ("seed",), "grail-ambiguous-scope")
        subjects.add(key)
        if scope["form"] in ("file-octets", "directory-metadata-fixture"):
            explicit_path(scope["path"])
        else:
            require(scope["path"] is None, "grail-opaque-scope-must-not-bind-a-path")
    for key, minimum, maximum in (
        ("max_attempts", 1, 128), ("max_depth", 0, 32), ("max_frames", 8, 512),
        ("max_total_octets", 1, 64 * 1024 * 1024),
    ):
        require(type(value[key]) is int and minimum <= value[key] <= maximum, "grail-root-budget")
    return value


def external_policy(image, policy):
    validate_policy(policy)
    kernel = image.kernel
    return kernel.ExternalPolicy(
        policy["manager_rappid"], policy["world_id"], SPEC_SHA256, MANIFEST_SHA256,
        frozenset(policy["rights"]),
        tuple(kernel.Scope(p["subject"]["namespace"], p["subject"]["native_key"], p["path"])
              for p in policy["scopes"]),
        sequence=policy["sequence"], expires_utc=policy["expires_utc"],
        max_attempts=policy["max_attempts"], max_depth=policy["max_depth"],
        max_frames=policy["max_frames"], max_total_octets=policy["max_total_octets"],
    )


def registry_frontier(workspace, policy_hash, binding_hash):
    identity, registry = identity_and_registry(workspace)
    return {
        "identity_sha256": sha(stable_read(Path(workspace) / "rappid.json", 65536)),
        "registry_sha256": sha(stable_read(Path(workspace) / "registry.json", manager().MAX_REGISTRY_BYTES)),
        "routing_sha256": measurement({
            "scan_roots": registry["scan_roots"], "workspaces": registry["workspaces"],
            "providers": registry["providers"], "editor_view": registry["editor_view"],
            "editor_views": registry["editor_views"],
        }),
        "suppression_sha256": measurement({
            "local": registry["forgotten"],
            "providers": {p: state["forgotten"] for p, state in registry["providers"].items()},
        }),
        "organization_sha256": measurement(registry["organization"]),
        "worlds_sha256": measurement({"manager": identity["world_id"],
                                     "pointers": [p["world_id"] for p in registry["workspaces"]]}),
        "policy_sha256": policy_hash, "binding_sha256": binding_hash,
    }


class Host:
    """Caller holds the existing manager lock; protocol and manager state share one COMMIT."""

    def __init__(self, workspace, *, now=None, initializing=False):
        self.workspace = explicit_path(workspace)
        self.path = self.workspace / ".grail"
        self.image, self.binding, self.binding_hash = load_runtime(workspace)
        self.c = None
        try:
            raw = owned_file(self.path / "policy.json")
            self.policy_doc, self.policy_hash = validate_policy(parse(raw)), sha(raw)
            require(self.policy_doc["manager_rappid"] == self.binding["manager_rappid"]
                    and self.policy_doc["world_id"] == self.binding["world_id"], "grail-policy-identity")
            self.policy = external_policy(self.image, self.policy_doc)
            self.fixture_clock = now
            self.now = now or clock()
            require(self.image.core.r.utc_valid(self.now)
                    and self.image.core.r.utc_valid(self.policy.expires_utc)
                    and self.now < self.policy.expires_utc, "grail-current-policy-expired")
            controller_path = self.path / "controller"
            private_directory(controller_path, create=initializing)
            for name in ("controller.sqlite3", "controller.sqlite3-journal", ".controller-lock"):
                info = safe_stat(controller_path / name, missing_ok=True)
                if info is not None:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                            and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
                            "grail-unsafe-controller-store")
            for name in ("controller.sqlite3-wal", "controller.sqlite3-shm"):
                require(safe_stat(controller_path / name, missing_ok=True) is None,
                        "grail-unqualified-controller-journal")
            exists = safe_stat(controller_path / "controller.sqlite3", missing_ok=True) is not None
            require(exists or (initializing and safe_stat(self.path / "state.json", missing_ok=True) is None),
                    "grail-controller-loss-never-remints-seed")
            kernel_controller = self.image.kernel.Controller

            class ManagerController(kernel_controller):
                @contextmanager
                def transaction(controller):
                    if controller.db.in_transaction:
                        controller.db.execute("SAVEPOINT manager_nested_operation")
                        try:
                            yield
                            controller.db.execute("RELEASE manager_nested_operation")
                        except BaseException:
                            controller.db.execute("ROLLBACK TO manager_nested_operation")
                            controller.db.execute("RELEASE manager_nested_operation")
                            raise
                    else:
                        with super().transaction():
                            yield

            # SQLite inherits the process umask when it creates the private database.
            old_mask = os.umask(0o077)
            try:
                self.c = ManagerController(self.image.core, controller_path, self.policy, now=self.now)
            finally:
                os.umask(old_mask)
            self.state = self.c._get("manager_state")
            if self.state is not None:
                validate_state(self.state)
                require(self.state["binding_sha256"] == self.binding_hash
                        and self.state["manager_rappid"] == self.policy.instance_rappid
                        and self.state["world_id"] == self.policy.world_id
                        and self.state["seed_lineage"] == [self.c._get("root")]
                        and self.state["adopted_projection_head"] == self.c._get("adoption_head"),
                        "grail-state-controller-mismatch")
                self.c.check_checkpoint(self.state["checkpoint"])
                recorded = {row[0]: row[1:] for row in self.c.db.execute(
                    "SELECT operation,request,candidate,record FROM adoptions")}
                accepted = {operation: entry for operation, entry in self.state["stages"].items()
                            if entry["status"] == "adopted"}
                require(set(recorded) == set(accepted), "grail-manager-decision-ledger-quarantine")
                for operation, entry in accepted.items():
                    job = self.state["jobs"][entry["job"]]
                    require(job["attempts"] and recorded[operation] ==
                            (entry["request"]["hash"], job["attempts"][-1]["result"]["hash"], entry["record"]["hash"]),
                            "grail-manager-decision-ledger-quarantine")
            else:
                require(initializing and self.c._get("root") is None,
                        "grail-missing-control-state-never-remints-seed")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.c is not None:
            self.c.close()
        self.image.close()

    def scope(self, descriptor):
        subject(descriptor)
        rows = [row for row in self.policy_doc["scopes"] if row["subject"] == descriptor]
        require(len(rows) == 1, "grail-outside-explicit-scope")
        return rows[0]

    def refresh_clock(self):
        self.now = self.fixture_clock or clock()
        self.c.now = self.now

    def current_frontier(self):
        require(sha(owned_file(self.path / "policy.json")) == self.policy_hash,
                "grail-external-policy-frontier-changed")
        require(sha(owned_file(self.path / "binding.json")) == self.binding_hash,
                "grail-external-binding-frontier-changed")
        return registry_frontier(self.workspace, self.policy_hash, self.binding_hash)

    @contextmanager
    def transaction(self):
        original = copy.deepcopy(self.state)
        try:
            with self.c.transaction():
                yield
                self.c._put("clock_floor", self.now)
                self.state["frontier"] = self.c.frontier()
                self.state["manager_frontier"] = self.current_frontier()
                self.state["adopted_projection_head"] = self.c._get("adoption_head")
                self.state["checkpoint"] = self.c.checkpoint()
                validate_state(self.state)
                self.c._put("manager_state", self.state)
        except BaseException:
            self.state = original
            raise

    def mirror(self):
        # A lost acknowledgement may leave this cache stale; only the SQLite state is authoritative.
        write_json(self.path / "state.json", self.state)


@contextmanager
def host(workspace, *, now=None):
    workspace = explicit_path(workspace)
    with manager_lock(workspace):
        value = Host(workspace, now=now)
        try:
            yield value
        finally:
            value.close()


def action_flags(**flags):
    for name, allowed in flags.items():
        require(allowed is True, "grail-explicit-" + name.replace("_", "-") + "-required")


def capture_guard(value, descriptor):
    value.refresh_clock()
    value.c.guard(descriptor, "capture")
    value.c.guard(descriptor, "retention")
    require(value.c._get("terminal_stop") is None, "grail-durable-root-stop")
    require(value.c._get("total_octets") < value.policy.max_total_octets,
            "grail-root-byte-budget-before-access")
    require(value.policy.max_frames - value.c.verify_history()["frames"] >= 8,
            "grail-root-frame-budget-before-access")


def fixture_path(value, path, form):
    path = explicit_path(path)
    parts = [part.casefold() for part in path.parts]
    require(not any(part in UNSAFE_COMPONENTS or part.startswith(".env")
                    or part.endswith((".pem", ".key", ".p12", ".pfx", ".app"))
                    or part in ("id_rsa", "id_ed25519", "token", "tokens") for part in parts),
            "grail-credential-or-native-fixture-refused-before-access")
    for root in (value.workspace, Path(value.binding["checkout"]), Path(value.binding["rapp1_path"])):
        require(not path.is_relative_to(root) and not root.is_relative_to(path),
                "grail-fixture-control-output-overlap")
    # Registered native locations are protection metadata, never locations to probe.
    registry = manager().load_registry(value.workspace)
    candidate = directory_info(path if form == "directory-metadata-fixture" else path.parent)
    protected_ids = [directory_identity(root) for root in
                     (value.workspace, value.binding["checkout"], value.binding["rapp1_path"])]
    for provider in registry["providers"].values():
        for root in provider["profileRoots"] + provider["requestedRoots"]:
            native = Path(root)
            require(not path.is_relative_to(native) and not native.is_relative_to(path),
                    "grail-native-profile-fixture-refused")
        protected_ids.extend(provider["profileIdentities"].values())
        protected_ids.extend(row["identity"] for row in provider["profileHistory"] if row["identity"] is not None)
    require(not any(identity in candidate["ancestors"] for identity in protected_ids),
            "grail-fixture-protected-filesystem-identity")
    return path


def directory_fixture(path, max_entries):
    require(type(max_entries) is int and 1 <= max_entries <= 128, "grail-directory-entry-bound")
    rows = []
    deadline = time.monotonic() + 10
    with directory_fd(path) as fd:
        before = os.fstat(fd)
        with os.scandir(fd) as entries:
            for number, entry in enumerate(entries):
                require(time.monotonic() < deadline, "grail-directory-time-bound")
                require(number < max_entries, "grail-directory-entry-bound")
                name = entry.name
                require(len(name.encode("utf-8")) <= 255 and not any(ord(c) < 32 for c in name),
                        "grail-untrusted-directory-name")
                lowered = name.casefold()
                require(lowered not in UNSAFE_COMPONENTS and not lowered.startswith(".env")
                        and not lowered.endswith((".pem", ".key", ".p12", ".pfx")),
                        "grail-credential-entry-refused")
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                require(not stat.S_ISLNK(info.st_mode), "grail-directory-link-refused")
                require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
                        "grail-directory-special-file-refused")
                require(not stat.S_ISREG(info.st_mode) or info.st_nlink == 1,
                        "grail-directory-hardlink-refused")
                rows.append({"name": name, "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
                             "bytes": info.st_size if stat.S_ISREG(info.st_mode) else None})
        after = os.fstat(fd)
        require(time.monotonic() < deadline, "grail-directory-time-bound")
        require((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
                "grail-directory-membership-changed")
    return encode({
        "form": "bounded-directory-metadata-fixture",
        "consistency": "one-level-metadata-not-coherent",
        "coverage": "entry-names-types-and-file-sizes-only",
        "entries": sorted(rows, key=lambda row: row["name"]),
        "native_rebinding": False, "contents_read": False,
    })


def new_job(value, name, descriptor, form, captured, *, migration=None):
    c = value.c
    original = c.body(captured["source"])
    fidelity = c._receipt("semantic_fidelity", captured["source"], "unproven",
                          "not-interpreted", "no-semantic-claim",
                          {"performed": False}, descriptor, original["restrictions"])
    authorization = c.authorization_receipt(descriptor, captured["source"], "local_synthesis")
    job = {
        "id": name, "subject": descriptor, "form": form, "source": captured["source"],
        "observations": [captured["source"]], "attempts": [],
        "receipts": {"rapp_integrity": captured["rapp_integrity"], "observation": captured["observation"],
                     "semantic_fidelity": fidelity, "current_authorization": authorization,
                     "safe_deployment": captured["safe_deployment"]},
        "outcome": "captured", "reason": None, "plan": None, "feedback": None,
        "migration": migration, "capture_frontier": value.current_frontier(),
    }
    value.state["jobs"][name] = job
    return job


def job_slot(value, name):
    slug(name)
    require(name not in value.state["jobs"], "grail-job-already-captured-use-existing-job")
    require(len(value.state["jobs"]) < MAX_JOBS, "grail-job-bound")


def decode_supplied(encoded):
    require(type(encoded) is str and len(encoded) <= 87384, "grail-finite-bounded-octets-required")
    raw = base64.b64decode(encoded, validate=True)
    require(base64.b64encode(raw).decode("ascii") == encoded, "grail-noncanonical-base64")
    return raw


def capture(workspace, job_id, descriptor, *, form, octets=None, path=None, max_entries=64,
            octets_base64=None, allow_capture=False, allow_retention=False,
            synthetic_fixture=False, now=None):
    action_flags(capture=allow_capture, retention=allow_retention)
    require(form in FORMS[:-1], "grail-unsupported-capture-form")
    if form != "supplied-octets":
        action_flags(synthetic_fixture=synthetic_fixture)
    with host(workspace, now=now) as value:
        job_slot(value, job_id)
        scope = value.scope(descriptor)
        require(scope["form"] == form, "grail-capture-form-outside-approved-scope")
        capture_guard(value, descriptor)
        restrictions = value.c.restrictions()
        consistency = "supplied-immutable-octets"
        if form != "supplied-octets":
            require(octets is None and octets_base64 is None and str(explicit_path(path)) == scope["path"],
                    "grail-exact-fixture-scope")
            approved = fixture_path(value, path, form)
            restrictions["rights"]["adoption"] = False
            if form == "file-octets":
                require(stat.S_ISREG(safe_stat(approved).st_mode), "grail-finite-regular-fixture-required")
                remaining = value.policy.max_total_octets - value.c._get("total_octets")
                octets = value.image.common.read_file(approved, min(value.image.kernel.MAX_OCTETS, remaining))
                consistency = "stable-descriptor-not-coherent"
            else:
                octets = directory_fixture(approved, max_entries)
        else:
            require(path is None, "grail-octets-capture-has-no-filesystem-path")
            if octets_base64 is not None:
                require(octets is None, "grail-ambiguous-supplied-octets")
                octets = decode_supplied(octets_base64)
        value.refresh_clock()
        with value.transaction():
            captured = value.c.capture_octets(descriptor, octets, inherited=[restrictions], consistency=consistency)
            job = new_job(value, job_id, descriptor, form, captured)
        value.mirror()
        return job_summary(value, job)


def migrate_metadata(workspace, job_id, *, allow_capture=False, allow_retention=False,
                     metadata_only=False, now=None):
    action_flags(capture=allow_capture, retention=allow_retention, metadata_only=metadata_only)
    descriptor = {"namespace": "manager-registry", "native_key": "routing"}
    with host(workspace, now=now) as value:
        job_slot(value, job_id)
        capture_guard(value, descriptor)
        frontier = value.current_frontier()
        registry = manager().load_registry(value.workspace)
        unresolved = [p["pointer_id"] for p in registry["workspaces"]
                      if p["pointer_version"] == 1 or "filesystemIdentity" not in p]
        for partition in registry["providers"].values():
            unresolved.extend(p["pointer_id"] for p in partition["catalog"]
                              if p["pointer_version"] == 1 or "profileIdentity" not in p)
            unresolved.extend(sorted(set(partition["selected"]) -
                                     {p["pointer_id"] for p in partition["catalog"]}))
            if partition["pending"] is not None or partition["status"] in ("refreshing", "stale"):
                unresolved.append("incomplete-native-catalog-frontier")
        original = stable_read(value.workspace / "registry.json", manager().MAX_REGISTRY_BYTES)
        require(sha(original) == frontier["registry_sha256"], "grail-registry-frontier-changed")
        raw = encode({
            "form": "existing-manager-registry-metadata", "registry": registry,
            "original_registry_b64": base64.b64encode(original).decode("ascii"),
            "coverage": "registry-metadata-only-not-native-behavior",
            "native_rebinding": False, "routed_sources_accessed": False,
        })
        restrictions = value.c.restrictions()
        if unresolved:
            restrictions["rights"]["adoption"] = False
        migration = {
            "registry_sha256": frontier["registry_sha256"], "unresolved": unresolved,
            "worlds": [registry["world_id"]] + [p["world_id"] for p in registry["workspaces"]],
            "behavior_coverage": "registry-metadata-only", "routes_changed": False,
        }
        with value.transaction():
            captured = value.c.capture_octets(descriptor, raw, inherited=[restrictions])
            job = new_job(value, job_id, descriptor, "registry-metadata", captured, migration=migration)
            require(value.current_frontier() == frontier, "grail-registry-frontier-changed")
        value.mirror()
        return job_summary(value, job)


def append_attempt(job, lens, result):
    job["attempts"].append({"lens": lens, "result": result["frame"], "kind": result["kind"],
                            "reason": result.get("reason")})
    for guarantee in ("rapp_integrity", "semantic_fidelity"):
        if guarantee in result:
            job["receipts"][guarantee] = result[guarantee]
    job["outcome"], job["reason"] = result["kind"], result.get("reason")


def stop_job(value, job, reason, lens=None, parents=()):
    c = value.c
    existing = c._get("terminal_stop")
    if existing is not None:
        stopped = {"kind": "stopped", "frame": existing, "reason": "durable-root-stop"}
    else:
        inputs = list(parents) or [job["source"]]
        restrictions = c.propagate([c.body(ref)["restrictions"] for ref in inputs])
        work = value.image.core.particle({"job": job["id"], "reason": reason, "parents": inputs})
        stopped = c._stop(job["subject"], work, reason, 0, restrictions, inputs)
    append_attempt(job, lens, stopped)
    return stopped


def execute_plan(value, job, strategy, field):
    c, descriptor = value.c, job["subject"]
    if c._get("terminal_stop") is not None:
        return stop_job(value, job, "durable-root-stop")
    if value.policy.max_frames - c.verify_history()["frames"] <= 2:
        return stop_job(value, job, "root-frame-budget")
    operation = "identity-octets" if strategy == "identity" else "json-field"
    source = c.body(job["source"])
    c.guard(descriptor, "local_synthesis", source["restrictions"])
    lens = c.synthesize(descriptor, job["source"], operation, "" if operation == "identity-octets" else field)
    result = c.execute(descriptor, lens, depth=0)
    append_attempt(job, lens, result)
    if result["kind"] != "refused":
        return result
    refusal = result["frame"]
    exhausted = c.execute(descriptor, lens, depth=0)
    append_attempt(job, lens, exhausted)
    if exhausted["reason"] != "repeated-state-fixed-point":
        return exhausted
    job["outcome"], job["reason"] = "refused", "stable-interpretation-refusal"
    if strategy != "adaptive":
        return result
    try:
        capture_guard(value, descriptor)
        inherited = [source["restrictions"], c.body(lens)["restrictions"],
                     c.body(refusal)["restrictions"], c.body(exhausted["frame"])["restrictions"]]
        # B's actual/synthesis read contains A's refusal and exhaust. Neither is authority.
        context = value.image.core.octets({
            "form": "retained-refusal-exhaust-context", "input_octets_b64": source["octets_b64"],
            "original_observation": job["source"], "refusal": c.body(refusal),
            "exhaust": c.body(exhausted["frame"]), "grants_authority": False,
        })
        require(value.policy.max_frames - c.verify_history()["frames"] >= 11,
                "grail-feedback-frame-budget")
        observed = c.capture_octets(descriptor, context, inherited=inherited)
    except (RoutingError, value.image.common.Refusal):
        return stop_job(value, job, "feedback-budget-or-rights-refused", lens,
                        [refusal, exhausted["frame"], job["source"]])
    job["observations"].append(observed["source"])
    job["feedback"] = {"refusal": refusal, "exhaust": exhausted["frame"], "source": observed["source"]}
    job["source"] = observed["source"]
    job["receipts"]["observation"] = observed["observation"]
    job["receipts"]["safe_deployment"] = observed["safe_deployment"]
    fallback = c.synthesize(descriptor, observed["source"], "identity-octets")
    result = c.execute(descriptor, fallback, depth=1)
    append_attempt(job, fallback, result)
    return result


def run_lenses(workspace, job_id, *, strategy="adaptive", field="workspace",
               allow_local_synthesis=False, allow_retention=False, allow_capture=False, now=None):
    action_flags(local_synthesis=allow_local_synthesis, retention=allow_retention)
    require(strategy in ("identity", "adaptive", "strict-field")
            and type(field) is str and len(field) <= 128, "grail-closed-safe-lens-plan")
    if strategy == "adaptive":
        action_flags(capture=allow_capture)
    with host(workspace, now=now) as value:
        c = value.c
        require(job_id in value.state["jobs"], "grail-unknown-job")
        job = value.state["jobs"][job_id]
        descriptor = job["subject"]
        value.refresh_clock()
        c.guard(descriptor, "local_synthesis")
        c.guard(descriptor, "retention")
        plan = {"strategy": strategy, "field": field}
        if job["plan"] is not None:
            require(job["plan"] == plan, "grail-job-plan-is-immutable")
            return job_summary(value, job)
        with value.transaction():
            job["plan"] = plan
            result = execute_plan(value, job, strategy, field)
            if result["kind"] == "candidate":
                if value.policy.max_frames - c.verify_history()["frames"] >= 3:
                    job["receipts"]["current_authorization"] = c.authorization_receipt(
                        descriptor, result["frame"], "adoption")
                    job["receipts"]["safe_deployment"] = c.deployment_receipt(descriptor, result["frame"])
        value.mirror()
        return job_summary(value, job)


def stage(workspace, job_id, operation_id, *, approve_identity_contract=False,
          allow_local_synthesis=False, allow_retention=False, now=None):
    action_flags(approve_identity_contract=approve_identity_contract,
                 local_synthesis=allow_local_synthesis, retention=allow_retention)
    slug(operation_id)
    with host(workspace, now=now) as value:
        require(job_id in value.state["jobs"], "grail-unknown-job")
        job, c = value.state["jobs"][job_id], value.c
        value.refresh_clock()
        c.guard(job["subject"], "local_synthesis")
        c.guard(job["subject"], "retention")
        existing = value.state["stages"].get(operation_id)
        if existing is not None:
            require(existing["job"] == job_id, "grail-operation-idempotency-conflict")
            return copy.deepcopy(existing)
        require(job["outcome"] == "candidate", "grail-no-successful-candidate-to-stage")
        require(len(value.state["stages"]) < MAX_JOBS, "grail-stage-bound")
        candidate = job["attempts"][-1]["result"]
        contract = identity_contract()
        with value.transaction():
            c.approve_contract(contract)
            proof = c.fidelity(job["subject"], candidate, contract)
            job["receipts"]["semantic_fidelity"] = proof
            request, protocol = c.request_adoption(
                job["subject"], candidate, proof, contract, operation_id,
                integrity=job["receipts"]["rapp_integrity"], observation=job["receipts"]["observation"])
            frontier = value.current_frontier()
            record = {"job": job_id, "request": request, "protocol_frontier": protocol,
                      "manager_frontier": frontier, "contract": contract, "status": "staged", "record": None,
                      "token": measurement({"request": request, "protocol": protocol, "manager": frontier})}
            value.state["stages"][operation_id] = record
            job["outcome"] = "staged"
        value.mirror()
        return copy.deepcopy(record)


def adoption_eligibility(value, job):
    require(job["form"] not in ("file-octets", "directory-metadata-fixture"),
            "grail-native-snapshot-adoption-disabled")
    if job["migration"] is not None:
        require(not job["migration"]["unresolved"],
                "grail-legacy-filesystem-identity-unresolved-explicit-safe-readd-required")
        require(job["migration"]["registry_sha256"] == value.current_frontier()["registry_sha256"],
                "grail-migration-registry-frontier-stale")


def adopt(workspace, operation_id, expected_frontier, *, allow_adoption=False,
          allow_retention=False, now=None, fault=None):
    action_flags(adoption=allow_adoption, retention=allow_retention)
    with host(workspace, now=now) as value:
        require(operation_id in value.state["stages"], "grail-unknown-staged-operation")
        stage_record, c = value.state["stages"][operation_id], value.c
        require(expected_frontier == stage_record["token"], "grail-external-complete-frontier-token-required")
        job = value.state["jobs"][stage_record["job"]]
        value.refresh_clock()
        c.guard(job["subject"], "adoption")
        c.guard(job["subject"], "retention")
        if stage_record["status"] == "adopted":
            # An acknowledgement is history, not renewed materialization permission.
            c.verify_history()
            return {"record": stage_record["record"], "idempotent": True, "authority": False}
        require(value.current_frontier() == stage_record["manager_frontier"],
                "grail-manager-complete-frontier-CAS-refused")
        adoption_eligibility(value, job)
        with value.transaction():
            adopted = c.adopt(job["subject"], stage_record["request"], stage_record["protocol_frontier"])
            stage_record["status"], stage_record["record"] = "adopted", adopted
            job["outcome"] = "adopted"
            row = c.db.execute(
                "SELECT frames.hash FROM frames JOIN receipts ON frames.hash=receipts.hash "
                "WHERE receipts.guarantee='current_authorization' AND receipts.subject=? ORDER BY frames.seq DESC LIMIT 1",
                (job["attempts"][-1]["result"]["hash"],),
            ).fetchone()
            require(row is not None, "grail-adoption-authorization-receipt-missing")
            job["receipts"]["current_authorization"] = {"space": "rapp/1:wave", "hash": row[0]}
            if fault:
                fault("before-commit")
            require(value.current_frontier() == stage_record["manager_frontier"],
                    "grail-manager-complete-frontier-CAS-refused")
        if fault:
            fault("after-commit")
        value.mirror()
        return {"record": adopted, "idempotent": False, "authority": False}


def initialize(workspace, scopes, *, rights, expires_utc, now=None,
               max_attempts=8, max_depth=4, max_frames=256, max_total_octets=1024 * 1024):
    require("retention" in rights, "grail-explicit-retention-required")
    workspace = explicit_path(workspace)
    with manager_lock(workspace):
        identity, _ = identity_and_registry(workspace)
        reserved = [
            {"subject": {"namespace": "manager-seed", "native_key": "root"}, "form": "seed", "path": None},
            {"subject": {"namespace": "manager-registry", "native_key": "routing"},
             "form": "registry-metadata", "path": None},
        ]
        require(type(scopes) is list and len(scopes) <= MAX_JOBS, "grail-scope-bound")
        for entry in scopes:
            closed(entry, {"subject", "form", "path"})
            subject(entry["subject"])
            require(entry["form"] in FORMS[:-1]
                    and entry["subject"].get("namespace") not in ("manager-seed", "manager-registry"),
                    "grail-reserved-controller-scope")
        policy = validate_policy({
            "schema": "rapp-workspace-manager/grail-policy/1", "version": 1, "spec_id": PROFILE,
            "manager_rappid": identity["rappid"], "world_id": identity["world_id"],
            "sequence": 1, "expires_utc": expires_utc, "rights": sorted(rights), "scopes": reserved + scopes,
            "max_attempts": max_attempts, "max_depth": max_depth, "max_frames": max_frames,
            "max_total_octets": max_total_octets,
        })
        binding_document(workspace)
        policy_path = workspace / ".grail/policy.json"
        old = owned_file(policy_path, missing=True)
        require(old is None or old == encode(policy), "grail-policy-change-requires-separate-reviewed-transition")
        if old is None:
            write_json(policy_path, policy)
        value = Host(workspace, now=now, initializing=True)
        try:
            if value.state is None:
                with value.c.transaction():
                    root = value.c.seed(reserved[0]["subject"])
                    value.state = {
                        "schema": STATE_SCHEMA, "version": 1, "spec_id": PROFILE,
                        "manager_rappid": identity["rappid"], "world_id": identity["world_id"],
                        "binding_sha256": value.binding_hash, "seed_lineage": [root],
                        "adopted_projection_head": None, "frontier": value.c.frontier(),
                        "manager_frontier": value.current_frontier(), "jobs": {}, "stages": {},
                        "projections": {"generation": 0, "focus": None, "files": [],
                                        "authority": False, "native_routes": False},
                        "checkpoint": value.c.checkpoint(),
                    }
                    validate_state(value.state)
                    value.c._put("manager_state", value.state)
            value.mirror()
            return {"seed": value.state["seed_lineage"][0], "identity_preserved": True,
                    "world_id": identity["world_id"], "root_budgets_preserved": True}
        finally:
            value.close()


def job_summary(value, job):
    value.refresh_clock()
    value.c.guard(job["subject"], "retention")
    guarantees = {}
    for guarantee, reference in job["receipts"].items():
        payload = value.c.body(reference)
        require(payload.get("guarantee") == guarantee and payload["validator_spec"] == PROFILE
                and payload["validator_pin"] == SPEC_SHA256, "grail-receipt-guarantee-substitution")
        row = value.c.db.execute("SELECT guarantee,subject FROM receipts WHERE hash=?",
                                 (reference["hash"],)).fetchone()
        require(row is not None and row[0] == guarantee and row[1] == payload["subject"]["hash"],
                "grail-receipt-is-not-controller-evidence")
        guarantees[guarantee] = {
            "status": payload["status"], "scope": payload["scope"], "method": payload["method"],
            "receipt": reference, "subject": payload["subject"], "authority": False,
        }
    return {
        "job": job["id"], "form": job["form"], "outcome": job["outcome"], "reason": job["reason"],
        "observations": job["observations"], "attempts": job["attempts"], "feedback": job["feedback"],
        "guarantees": guarantees, "migration": job["migration"],
        "current_authorization_is_a_snapshot_not_a_capability": True,
        "native_rebinding": False, "learned_semantic_capability": "disabled-unproven",
    }


def projection_status(value):
    files = []
    for entry in value.state["projections"]["files"]:
        try:
            raw = owned_file(value.path / entry["name"], limit=MAX_STATE)
            current = len(raw) == entry["bytes"] and sha(raw) == entry["sha256"]
        except (OSError, RoutingError):
            current = False
        files.append({"name": entry["name"], "matches_committed_projection": current})
    frontier = value.current_frontier()
    focus = value.state["projections"]["focus"]
    freshness = all(stage_record["manager_frontier"] == frontier
                    for stage_record in value.state["stages"].values()
                    if stage_record["status"] == "adopted"
                    and (focus is None or stage_record["job"] == focus))
    return {"authority": False, "files": files, "manager_frontier_current": freshness,
            "recovery_required": any(not p["matches_committed_projection"] for p in files),
            "native_routes": False}


def inspect(workspace, *, job_id=None, now=None):
    with host(workspace, now=now) as value:
        for scope in value.policy_doc["scopes"]:
            value.c.guard(scope["subject"], "retention")
        if job_id is not None:
            require(job_id in value.state["jobs"], "grail-unknown-job")
        jobs = [value.state["jobs"][job_id]] if job_id is not None else list(value.state["jobs"].values())
        return {
            **runtime.contract(), "schema": STATE_SCHEMA,
            "seed_lineage": value.state["seed_lineage"],
            "adopted_projection_head": value.state["adopted_projection_head"],
            "controller_frontier": value.c.frontier(), "manager_frontier": value.current_frontier(),
            "root_budget": {"attempts_used": value.c._get("attempts"), "max_attempts": value.policy.max_attempts,
                            "frames_used": value.c.verify_history()["frames"], "max_frames": value.policy.max_frames,
                            "octets_used": value.c._get("total_octets"), "max_total_octets": value.policy.max_total_octets,
                            "terminal_stop": value.c._get("terminal_stop")},
            "jobs": [job_summary(value, job) for job in jobs],
            "projections": projection_status(value), "signed_grail_activation": False,
            "assurance_receipts_are_not_authority": True,
        }


def history(workspace, *, allow_retention=False, now=None):
    action_flags(retention=allow_retention)
    workspace = explicit_path(workspace)
    with manager_lock(workspace):
        image, binding, _ = load_runtime(workspace, historical=True)
        try:
            policy = validate_policy(parse(owned_file(workspace / ".grail/policy.json")))
            current = now or clock()
            require(image.core.r.utc_valid(current) and image.core.r.utc_valid(policy["expires_utc"])
                    and current < policy["expires_utc"] and "retention" in policy["rights"],
                    "grail-historical-retention-not-currently-authorized")
            path = workspace / ".grail/controller"
            private_directory(path)
            owned_file(path / "controller.sqlite3", limit=64 * 1024 * 1024)
            for suffix in ("-journal", "-wal", "-shm"):
                info = safe_stat(path / ("controller.sqlite3" + suffix), missing_ok=True)
                require(info is None or info.st_size == 0, "grail-recover-controller-before-historical-read")
            database = sqlite3.connect((path / "controller.sqlite3").as_uri() + "?mode=ro", uri=True)
            try:
                database.execute("PRAGMA query_only=ON")
                database.execute("PRAGMA trusted_schema=OFF")
                stored = database.execute("SELECT value FROM meta WHERE key='policy'").fetchone()
                expected = external_policy(image, policy)
                # The policy comparison uses the canonical controller's representation, without opening a writer.
                shell = object.__new__(image.kernel.Controller)
                require(stored and image.core.parse(stored[0]) == shell._policy_value(expected),
                        "grail-historical-policy-substitution")
                floor = database.execute("SELECT value FROM meta WHERE key='clock_floor'").fetchone()
                require(floor and current >= image.core.parse(floor[0]), "grail-controller-clock-rollback")
                rows = database.execute("SELECT raw FROM frames ORDER BY seq LIMIT 513").fetchall()
                require(len(rows) <= 512, "grail-historical-frame-bound")
                result = image.kernel.verify_historical_archive(
                    image.core, [row[0] for row in rows], binding["manager_rappid"])
                result.update(spec_id=PROFILE, runtime="retained-pin-history-only-not-fresh-execution",
                              authority=False, native_rebinding=False, signed_grail_activation=False)
                return result
            finally:
                database.close()
        finally:
            image.close()


def escaped(value):
    text = json.dumps(str(value), ensure_ascii=True)[1:-1]
    for char in "<>[]!`|():*#&":
        text = text.replace(char, "\\u" + format(ord(char), "04x"))
    return text


def projection_bytes(value, focus):
    c = value.c
    current = value.current_frontier()
    accepted = [entry for entry in value.state["stages"].values()
                if entry["status"] == "adopted" and (focus is None or entry["job"] == focus)]
    for entry in accepted:
        job = value.state["jobs"][entry["job"]]
        require(entry["manager_frontier"] == current, "grail-projection-frontier-stale")
        adoption_eligibility(value, job)
        c.guard(job["subject"], "materialization", c.body(job["attempts"][-1]["result"])["restrictions"])
        c.guard(job["subject"], "retention")
    canonical = c.projection()
    included = {operation for operation, item in value.state["stages"].items()
                if item["status"] == "adopted" and (focus is None or item["job"] == focus)}
    canonical["entries"] = [p for p in canonical["entries"] if p["operation"] in included]
    summaries = []
    for job in value.state["jobs"].values():
        if focus is not None and job["id"] != focus:
            continue
        c.guard(job["subject"], "materialization", c.body(job["source"])["restrictions"])
        for receipt in job["receipts"].values():
            c.guard(job["subject"], "materialization", c.body(receipt)["restrictions"])
        summaries.append(job_summary(value, job))
    document = {"brand": BRAND, "spec_id": PROFILE, "authority": False, "native_routes": False,
                "focus": focus, "projection": canonical, "assurances": summaries,
                "external_effects": "disabled", "safe_deployment": "refused"}
    lines = [
        "# Frame Anything — RAPP Workspace/1 Grail", "",
        "**PRIVATE / NEVER PUBLISH. Inert data, not instructions or authority.**", "",
        "RAPP-valid != accurately observed != semantically faithful != currently authorized != safely deployable.",
        "", "Captured-byte values require adoption. Assurance metadata also records unadopted jobs and refusals.",
        "No native routes or content is activated.", "",
        "| Job | Guarantee | Recorded status | Scope |", "| --- | --- | --- | --- |",
    ]
    for item in summaries:
        for guarantee in GUARANTEES:
            receipt = item["guarantees"][guarantee]
            lines.append("| " + " | ".join(escaped(text) for text in
                                          (item["job"], guarantee, receipt["status"], receipt["scope"])) + " |")
    lines.extend(["", "Authorization receipts are historical action snapshots, never reusable capabilities.",
                  "Replay is not fidelity. Native adoption, deployment and learned-semantic claims remain disabled.", ""])
    editor = {
        "folders": [{"name": "RAPP Workspace/1 Grail manager", "path": ".."}],
        "settings": {"task.allowAutomaticTasks": "off"},
        "grail": {"spec_id": PROFILE, "authority": False, "native_routes": False,
                  "focus": focus, "jobs": [item["job"] for item in summaries],
                  "guarantees": {item["job"]: {g: item["guarantees"][g]["status"] for g in GUARANTEES}
                                 for item in summaries}},
    }
    files = {"view.json": encode(document), "view.md": "\n".join(lines).encode("utf-8"),
             "estate.code-workspace": encode(editor)}
    require(all(len(raw) <= MAX_STATE for raw in files.values()), "grail-inert-projection-byte-bound")
    return files


def materialize(workspace, *, job_id=None, allow_materialization=False, allow_retention=False,
                now=None, fault=None):
    action_flags(materialization=allow_materialization, retention=allow_retention)
    with host(workspace, now=now) as value:
        require(job_id is None or job_id in value.state["jobs"], "grail-unknown-focus")
        value.refresh_clock()
        for scope in value.policy_doc["scopes"]:
            value.c.guard(scope["subject"], "materialization")
            value.c.guard(scope["subject"], "retention")
        files = projection_bytes(value, job_id)
        entries = [{"name": name, "sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())]
        with value.transaction():
            previous = value.state["projections"]
            value.state["projections"] = {
                "generation": previous["generation"] + int(previous["files"] != entries or previous["focus"] != job_id),
                "focus": job_id, "files": entries, "authority": False, "native_routes": False,
            }
        if fault:
            fault("after-projection-commit")
        for name, raw in files.items():
            value.refresh_clock()
            for scope in value.policy_doc["scopes"]:
                value.c.guard(scope["subject"], "materialization")
                value.c.guard(scope["subject"], "retention")
            require(value.current_frontier() == value.state["manager_frontier"],
                    "grail-projection-frontier-changed-before-write")
            atomic_text(value.path / name, raw.decode("utf-8"))
            if fault:
                fault("after-" + name)
        value.mirror()
        return {"authority": False, "native_routes": False, "files": entries,
                "generation": value.state["projections"]["generation"]}


def recover(workspace, *, allow_retention=False, allow_materialization=False, now=None):
    action_flags(retention=allow_retention)
    with host(workspace, now=now) as value:
        for scope in value.policy_doc["scopes"]:
            value.c.guard(scope["subject"], "retention")
        value.c.verify_history()
        value.mirror()
        focus = value.state["projections"]["focus"]
    if allow_materialization:
        return materialize(workspace, job_id=focus, allow_materialization=True, allow_retention=True, now=now)
    return {"recovered": "controller-state-cache-only", "views_written": False, "authority": False}


def demo(checkout, rapp1_path, output):
    output = Path(output)
    require(not output.is_absolute() and ".." not in output.parts and output != Path("."),
            "grail-demo-requires-fresh-relative-owned-output")
    path = Path.cwd() / output
    require(not path.exists(), "grail-demo-output-exists-never-reset-a-seed")
    files = runtime.capture_checkout(checkout)
    image = runtime.Runtime(checkout, rapp1_path, files)
    try:
        rid = image.core.r.mint_rappid("fictional", "grail-manager-demo")
    finally:
        image.close()
    private_directory(path, create=True)
    identity = {"schema": "rapp/1", "rappid": rid, "kind": "workspace", "role": "manager",
                "name": "synthetic-grail-manager", "mode": "solo", "world_id": "synthetic-fixture-world"}
    write_json(path / "rappid.json", identity)
    write_json(path / "registry.json", {
        "schema": manager().REGISTRY_SCHEMA, "manager_rappid": rid, "world_id": identity["world_id"],
        "generated_utc": "2026-09-15T03:12:29.000Z", "scan_roots": [], "workspaces": [],
        "providers": {}, "forgotten": [], "editor_view": "estate.code-workspace",
        "editor_views": ["estate.code-workspace"], "organization": manager().default_organization(),
    })
    atomic_text(path / "README.md", "# PRIVATE / NEVER PUBLISH\n\nSynthetic metadata-only demo manager.\n")
    bind(path, checkout, rapp1_path)
    cases = [
        ("nested-array", b'[["radically",{"nested":[1,2,3]}],null]', "adaptive"),
        ("binary-octets", b"\x00\xff\xfeSYNTHETIC\x00\x10", "adaptive"),
        ("stable-refusal", b'{"unsupported_native_shape":["unknown"]}', "strict-field"),
    ]
    scopes = [{"subject": {"namespace": "synthetic-fixture", "native_key": name},
               "form": "supplied-octets", "path": None} for name, _, _ in cases]
    initialize(path, scopes, rights=set(RIGHTS), expires_utc="2099-01-01T00:00:00.000Z")
    results = []
    for (name, raw, strategy), approved in zip(cases, scopes):
        capture(path, name, approved["subject"], form="supplied-octets", octets=raw,
                allow_capture=True, allow_retention=True)
        run_lenses(path, name, strategy=strategy, allow_local_synthesis=True, allow_retention=True,
                   allow_capture=True)
        if strategy == "adaptive":
            prepared = stage(path, name, "accept-" + name, approve_identity_contract=True,
                             allow_local_synthesis=True, allow_retention=True)
            adopt(path, "accept-" + name, prepared["token"], allow_adoption=True, allow_retention=True)
        results.append(inspect(path, job_id=name)["jobs"][0])
    projections = materialize(path, allow_materialization=True, allow_retention=True)
    status = inspect(path)
    report = {
        **runtime.contract(), "public_synthetic_only": True, "results": results,
        "rapp_frames_verified": status["root_budget"]["frames_used"],
        "root_budget": status["root_budget"], "projection_files": projections["files"],
        "safe_deployment": "refused", "signed_grail_activation": False,
        "learning_claim": "none; deterministic bounded lenses, not learned native semantics",
    }
    write_json(path / ".grail/demo-report.json", report)
    return report


def parse_subject(text):
    require(type(text) is str and ":" in text, "grail-subject-must-be-namespace-colon-key")
    namespace, key = text.split(":", 1)
    return subject({"namespace": namespace, "native_key": key})


def register_cli(subparsers):
    parser = subparsers.add_parser(
        "grail", help="Frame Anything: pinned safe lenses and inert local projections",
        description=BRAND + ": five guarantees, never one authority Boolean. "
                    "No network discovery, native grafts, model calls or deployment.")
    commands = parser.add_subparsers(dest="grail_command", required=True)

    def command(name, help_text, flags=(), workspace=True):
        child = commands.add_parser(name, help=help_text, description=help_text)
        if workspace:
            child.add_argument("--workspace", required=True, help="explicit absolute existing private manager")
        for flag in flags:
            child.add_argument("--" + flag.replace("_", "-"), action="store_true")
        child.set_defaults(run=dispatch)
        return child

    command("contract", "Print the exact expected Grail spec/manifest/parent pins; no I/O.", workspace=False)
    binding = command("bind", "Bind an explicit canonical checkout by exact manifest hashes; no discovery.")
    binding.add_argument("--protocol-checkout", required=True)
    binding.add_argument("--rapp1-path", required=True)
    command("verify", "Reverify every pinned closure byte and explicit parent; never use legacy validators.")
    initialization = command("init", "Preserve the manager RAPPID and initialize or reuse exactly one seed.",
                             tuple("allow_" + right for right in RIGHTS))
    initialization.add_argument("--scopes-file", help="explicit absolute host-selected closed JSON scope list")
    initialization.add_argument("--expires-utc", required=True, help="external policy expiry: YYYY-MM-DDTHH:MM:SS.sssZ")
    for name, default in (("max_attempts", 8), ("max_depth", 4), ("max_frames", 256),
                          ("max_total_octets", 1024 * 1024)):
        initialization.add_argument("--" + name.replace("_", "-"), type=int, default=default)
    capturing = command("capture", "Capture a finite declared fixture only with separate capture and retention grants.",
                        ("allow_capture", "allow_retention", "synthetic_fixture"))
    capturing.add_argument("--job", required=True)
    capturing.add_argument("--subject", required=True, help="exact approved namespace:native-key")
    capturing.add_argument("--form", choices=FORMS[:-1], required=True)
    source = capturing.add_mutually_exclusive_group(required=True)
    source.add_argument("--octets-base64", help="finite immutable supplied bytes; no file access")
    source.add_argument("--fixture", help="exact absolute approved fixture file or one-level metadata directory")
    capturing.add_argument("--max-entries", type=int, default=64, help="directory entry bound, at most 128; no recursion")
    running = command("run", "Run the pinned total evaluator; retain A refusal/exhaust as B input, sharing root budgets.",
                      ("allow_local_synthesis", "allow_retention", "allow_capture"))
    running.add_argument("--job", required=True)
    running.add_argument("--strategy", choices=("identity", "adaptive", "strict-field"), default="adaptive")
    running.add_argument("--field", default="workspace", help="exact JSON field for lens A; not a program")
    staging = command("stage", "Externally approve the exact byte identity contract; stage an inert request, not adoption.",
                      ("approve_identity_contract", "allow_local_synthesis", "allow_retention"))
    staging.add_argument("--job", required=True)
    staging.add_argument("--operation-id", required=True)
    adopting = command("adopt", "External controller complete-frontier transaction; exact retries are idempotent.",
                       ("allow_adoption", "allow_retention"))
    adopting.add_argument("--operation-id", required=True)
    adopting.add_argument("--expected-frontier", required=True, help="exact stage token; receipts cannot supply authority")
    migration = command("migrate", "Observe registry metadata only; preserve pointers/worlds/order/suppression without source I/O.",
                        ("metadata_only", "allow_capture", "allow_retention"))
    migration.add_argument("--job", required=True)
    for name in ("inspect", "status", "tree"):
        child = command(name, "Inspect five separate receipt states without granting authority or opening routes.")
        child.add_argument("--job")
    command("history", "Verify retained RAPP frames without requiring the old evaluator; never renew authorization.",
            ("allow_retention",))
    for name in ("project", "focus", "recover"):
        child = command(name, "Rebuild fixed manager-owned inert data views; never native routes, instructions or code.",
                        ("allow_materialization", "allow_retention"))
        if name == "focus":
            child.add_argument("--job", required=True)
    effect = command("effect", "Explicit refusal for unqualified operations before any source access.", workspace=False)
    effect.add_argument("--operation", required=True)
    demonstration = command("demo", "One-command synthetic Frame Anything: two shapes, A exhaust to B, and stable refusal.",
                            workspace=False)
    demonstration.add_argument("--protocol-checkout", required=True)
    demonstration.add_argument("--rapp1-path", required=True)
    demonstration.add_argument("--output", default=".validation/grail-manager-demo")
    return parser


def dispatch(args):
    try:
        name = args.grail_command
        if name == "contract":
            result = runtime.contract()
        elif name == "effect":
            raise RoutingError("grail-unqualified-effect-disabled-before-access")
        elif name == "bind":
            result = bind(args.workspace, args.protocol_checkout, args.rapp1_path)
        elif name == "verify":
            with manager_lock(explicit_path(args.workspace)):
                image, _, binding_hash = load_runtime(args.workspace)
                image.close()
            result = {**runtime.contract(), "verified": True, "binding_sha256": binding_hash}
        elif name == "init":
            action_flags(retention=args.allow_retention)
            scopes = parse(stable_read(explicit_path(args.scopes_file), 65536)) if args.scopes_file else []
            result = initialize(args.workspace, scopes,
                                rights={right for right in RIGHTS if getattr(args, "allow_" + right)},
                                expires_utc=args.expires_utc, max_attempts=args.max_attempts,
                                max_depth=args.max_depth, max_frames=args.max_frames,
                                max_total_octets=args.max_total_octets)
        elif name == "capture":
            action_flags(capture=args.allow_capture, retention=args.allow_retention)
            result = capture(args.workspace, args.job, parse_subject(args.subject), form=args.form,
                             octets_base64=args.octets_base64, path=args.fixture, max_entries=args.max_entries,
                             allow_capture=args.allow_capture, allow_retention=args.allow_retention,
                             synthetic_fixture=args.synthetic_fixture)
        elif name == "run":
            result = run_lenses(args.workspace, args.job, strategy=args.strategy, field=args.field,
                                allow_local_synthesis=args.allow_local_synthesis,
                                allow_retention=args.allow_retention, allow_capture=args.allow_capture)
        elif name == "stage":
            result = stage(args.workspace, args.job, args.operation_id,
                           approve_identity_contract=args.approve_identity_contract,
                           allow_local_synthesis=args.allow_local_synthesis, allow_retention=args.allow_retention)
        elif name == "adopt":
            result = adopt(args.workspace, args.operation_id, args.expected_frontier,
                           allow_adoption=args.allow_adoption, allow_retention=args.allow_retention)
        elif name == "migrate":
            result = migrate_metadata(args.workspace, args.job, allow_capture=args.allow_capture,
                                      allow_retention=args.allow_retention, metadata_only=args.metadata_only)
        elif name in ("inspect", "status", "tree"):
            result = inspect(args.workspace, job_id=args.job)
        elif name == "history":
            result = history(args.workspace, allow_retention=args.allow_retention)
        elif name == "recover":
            result = recover(args.workspace, allow_retention=args.allow_retention,
                             allow_materialization=args.allow_materialization)
        elif name in ("project", "focus"):
            result = materialize(args.workspace, job_id=getattr(args, "job", None),
                                 allow_retention=args.allow_retention,
                                 allow_materialization=args.allow_materialization)
        else:
            result = demo(args.protocol_checkout, args.rapp1_path, args.output)
        print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
        return 0
    except (RoutingError, ValueError, OSError, sqlite3.Error) as error:
        print("REFUSED: " + json.dumps(str(error), ensure_ascii=True), file=sys.stderr)
        return 1
