#!/usr/bin/env python3
"""Operate a private pointer-only RAPP manager and its disposable projections."""

import argparse
import copy
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent))
import native_ai
from routing_io import (
    Budget, Limits, RoutingError, absolute_path, atomic_json, atomic_text,
    directory_fd, directory_identity, directory_info, directories_overlap,
    ensure_output, manager_lock, native_path, protected_local, read_bytes, read_json,
    reject_constant, resolve_protected_boundary, safe_stat, same_directory, same_location, unique_object,
    validate_filesystem_identity, verified_directory, verified_directory_info,
)


REGISTRY_SCHEMA = "rapp-workspace-manager/1"
MAX_REGISTRY_BYTES = 512 * 1024 * 1024
LOCAL_FIELDS = {
    "name", "path", "kind", "rappid", "mode", "world_id", "tags",
    "pointer_version", "pointer_type", "pointer_id", "selection",
    "filesystemIdentity",
}
PROVIDER_FIELDS = {
    "profileRoots", "requestedRoots", "catalog", "selected", "forgotten", "status",
    "error", "last_attempt_utc", "last_success_utc", "pending", "observations",
    "profileIdentities", "profileHistory",
}
PRUNED_DIRS = {
    ".cache", ".git", ".next", ".parcel-cache", ".venv", "__pycache__",
    "build", "dist", "node_modules", "target", "vendor",
    ".copilot", ".claude", ".hermes", ".scout", ".grokbot", ".grok",
}


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def find_rapp1(explicit=None):
    for candidate in (
        explicit, os.environ.get("RAPP1_PATH"),
        "~/Documents/GitHub/rapp-1", "~/rapp-1", "~/src/rapp-1",
    ):
        if candidate and (Path(candidate).expanduser() / "rapp.py").is_file():
            return Path(candidate).expanduser().resolve()
    raise SystemExit("rapp.py not found; pass --rapp1-path or set RAPP1_PATH")


def load_rapp(rapp1_path):
    sys.path.insert(0, str(rapp1_path))
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import rapp
        return rapp
    finally:
        sys.dont_write_bytecode = previous_bytecode


def manager_identity(workspace):
    workspace = absolute_path(workspace)
    if protected_local(workspace):
        raise RoutingError("native-store-cannot-be-manager")
    identity = read_json(workspace / "rappid.json", max_bytes=65536)
    if (
        not isinstance(identity, dict) or identity.get("schema") != "rapp/1"
        or identity.get("kind") != "workspace" or identity.get("role") != "manager"
        or identity.get("mode") != "solo"
    ):
        raise RoutingError("not-a-private-manager")
    native_ai.text(identity.get("rappid"))
    native_ai.text(identity.get("world_id"))
    return identity


def discover_git_workspaces(root, budget=None, exclude=()):
    root = absolute_path(root)
    if protected_local(root):
        raise RoutingError("broad-or-native-scan-root")
    budget = budget or Budget()
    excluded = set()
    for value in exclude:
        saved, info = resolve_protected_boundary(value)
        if saved is not None:
            excluded.add(tuple(saved))
        if info is not None and info["identity"] is not None:
            excluded.add(tuple(info["identity"]))
    visited = set()
    found, queue = [], [(root, 0)]
    while queue:
        current, depth = queue.pop()
        key = tuple(directory_identity(current))
        if key in excluded or key in visited:
            continue
        visited.add(key)
        budget.check()
        if depth > 64:
            raise RoutingError("depth-bound")
        children = []
        with directory_fd(current) as fd:
            with os.scandir(fd) as entries:
                for entry in entries:
                    budget.entry()
                    if entry.is_symlink():
                        continue
                    if entry.name == ".git" and (
                        entry.is_dir(follow_symlinks=False) or entry.is_file(follow_symlinks=False)
                    ):
                        found.append(current)
                    if entry.name not in PRUNED_DIRS and entry.is_dir(follow_symlinks=False):
                        child = current / entry.name
                        if not protected_local(child):
                            children.append(child)
        queue.extend((child, depth + 1) for child in sorted(children, reverse=True))
    return sorted(set(found), key=lambda path: str(path).casefold())


def local_id(path):
    return native_ai.pointer_id("local", absolute_path(path), "local-directory", None)


def legacy_local_id(path):
    return native_ai.legacy_pointer_id("local", str(path), "local-directory", None)


def legacy_requested_ids(value):
    canonical = absolute_path(value)
    previous_spelling = Path(os.path.abspath(Path(os.path.expanduser(os.fspath(value)))))
    return {legacy_local_id(canonical), legacy_local_id(previous_spelling)}


def local_pointer_id(identity):
    return native_ai.routing_id("local", identity, "local-directory", None)


def read_workspace_pointer(path, rapp_module, *, exact=False, budget=None):
    path = absolute_path(path)
    if protected_local(path):
        raise RoutingError("native-store-not-workspace")
    filesystem_id = directory_identity(path)
    kind = "git"
    if exact:
        try:
            git = safe_stat(path / ".git", missing_ok=True)
            kind = "git" if git and (stat.S_ISDIR(git.st_mode) or stat.S_ISREG(git.st_mode)) else "directory"
        except RoutingError:
            kind = "directory"
    pointer = {
        "name": path.name, "path": str(path), "kind": kind,
        "mode": None, "world_id": None, "rappid": None, "tags": [],
        "pointer_version": 2, "pointer_type": "local-directory",
        "pointer_id": local_pointer_id(filesystem_id),
        "filesystemIdentity": filesystem_id, "selection": "exact" if exact else "discovered",
    }
    try:
        identity = read_json(path / "rappid.json", budget, max_bytes=65536)
    except RoutingError as error:
        if error.code in ("time-bound", "byte-bound"):
            raise
        if directory_identity(path) != filesystem_id:
            raise RoutingError("metadata-changed")
        if directory_identity(path) != filesystem_id:
            raise RoutingError("metadata-changed")
        return pointer
    if not isinstance(identity, dict):
        if directory_identity(path) != filesystem_id:
            raise RoutingError("metadata-changed")
        return pointer
    tags = identity.get("tags", [])
    if (
        not isinstance(tags, list) or len(tags) > 32
        or not all(isinstance(tag, str) and 0 < len(tag) <= 128 and not any(ord(c) < 32 for c in tag) for tag in tags)
    ):
        tags = []
    if (
        identity.get("schema") == "rapp/1" and identity.get("kind") == "workspace"
        and rapp_module.rappid_valid(identity.get("rappid"))
    ):
        world = identity.get("world_id")
        if not isinstance(world, str) or len(world) > 4096 or any(ord(c) < 32 for c in world):
            world = None
        pointer.update(
            kind="rapp-workspace", rappid=identity["rappid"], tags=tags, world_id=world,
            mode=identity.get("mode") if identity.get("mode") in ("solo", "hive") else None,
        )
    return pointer


def md(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("`", "&#96;").replace("\n", " ")


def render_home(identity, registry):
    entries = registry["workspaces"]
    rows = [
        f"| {md(item['name'])} | {item['kind']} | {item['mode'] or '-'} | "
        f"`{md(item['path'])}` | {md(', '.join(item['tags']) or '-')} |"
        for item in entries
    ]
    table = "\n".join(rows) or "| _No workspaces found_ | - | - | - | - |"
    provider_rows, candidate_rows = [], []
    for provider, state in sorted(registry.get("providers", {}).items()):
        provider_rows.append(
            f"| {provider} | {state['status']} | {len(state['catalog'])} | "
            f"{len(state['selected'])} | {md(state['error'] or '-')} |"
        )
        selected = set(state["selected"])
        ordered = sorted(state["catalog"], key=lambda item: (item["pointer_id"] not in selected, item["pointer_id"]))
        for item in ordered[:100]:
            selection = "selected" if item["pointer_id"] in selected else "candidate"
            candidate_rows.append(
                f"| {provider} | {md(native_ai.describe(item))} | {selection} | "
                f"{md(native_ai.routing_hint(item))} | `{item['pointer_id']}` |"
            )
        for observation in state["observations"]:
            candidate_rows.append(
                "| grokbot | app-detected | observation only | workspace-mapping-unavailable | "
                f"`{observation['observation_id']}` |"
            )
    providers = "\n".join(provider_rows) or "| _None inspected_ | - | 0 | 0 | - |"
    candidates = "\n".join(candidate_rows) or "| _No native candidates_ | - | - | - | - |"
    return f"""# Local Workspace Manager

**PRIVATE / NEVER PUBLISH.** This dashboard contains pointers only. It must
never absorb files or content from the workspaces it routes.

- Manager: `{identity["rappid"]}`
- World: `{identity["world_id"]}`
- Last registry change: `{registry["generated_utc"]}`
- Registered local roots: **{len(entries)}**
- RAPP Workspaces: **{sum(item["kind"] == "rapp-workspace" for item in entries)}**

## Workspaces

| Name | Kind | Mode | Local path | Tags |
| --- | --- | --- | --- | --- |
{table}

## Native provider catalogs

Refresh is observation, not selection. Stale catalogs retain last-good metadata.
Native roots and stores remain authoritative, including unresolved and nonlocal
roots; the manager never invents a local path for them.

| Provider | Scan state | Candidates | Selected IDs | Error |
| --- | --- | --- | --- | --- |
{providers}

At most 100 candidates per provider are shown (selected IDs first).
`provider list` exposes the bounded full catalog. No chat-derived names are used.

| Provider | Native identity | Routing selection | Mapping | Pointer ID |
| --- | --- | --- | --- | --- |
{candidates}

## Commands

```bash
python3 tools/workspace_manager.py scan --workspace . --root ~/src
python3 tools/workspace_manager.py list --workspace .
python3 tools/workspace_manager.py open --workspace . --name <workspace-name>
python3 tools/workspace_manager.py editor-view --workspace .
python3 tools/workspace_manager.py provider list --workspace . --provider copilot
```

`registry.json` is the routing authority. HOME and the editor view are disposable
projections. Source projects and native provider stores retain all other authority.
"""


def write_home(workspace, identity, registry):
    atomic_text(Path(workspace) / "HOME.md", render_home(identity, registry))


def init_manager(args):
    workspace = absolute_path(args.workspace)
    if protected_local(workspace):
        raise RoutingError("native-store-cannot-be-manager")
    rapp = load_rapp(find_rapp1(args.rapp1_path))
    with directory_fd(workspace, create=True) as fd:
        with os.scandir(fd) as entries:
            if next(entries, None) is not None:
                raise RoutingError("init-requires-empty-private-directory")
    rappid = rapp.mint_rappid(args.owner, args.slug)
    if not rapp.rappid_valid(rappid):
        raise SystemExit("minted rappid failed validation")
    identity = {
        "schema": "rapp/1", "rappid": rappid, "kind": "workspace", "role": "manager",
        "name": args.slug, "mode": "solo", "world_id": args.world_id,
    }
    atomic_json(workspace / "rappid.json", identity)
    files = {
        "README.md": """# PRIVATE / NEVER PUBLISH

This private manager stores selected pointers, never project or native AI content.
Do not publish, mirror, attach a public remote, or copy routed content here.
Source workspaces/native stores remain authoritative. Clear/forget affect only
manager-owned pointers and projections. No native deletion/disconnection is allowed.
""",
        "CLAUDE.md": """# Manager operating contract

Read registry.json for routing authority. HOME.md and estate.code-workspace are
generated views. Preserve world boundaries and native provider identities.
Use explicit owner selection. Never read project content or native transcripts,
prompts, summaries, memories, credentials, attachments or browser state.
Never delete, move, clone, edit, publish or disconnect a routed project/native store.
""",
        "OWNER.md": "# Owner\n\nThe local owner is sovereign; keep personal details outside routing metadata.\n",
        "where-everything-lives.md": """# Where everything lives

- registry.json: manager-owned routing pointers, selections and suppressions.
- HOME.md / estate.code-workspace: disposable projections.
- rappid.json: mint-once RAPP/1 identity.
- rapp-projects/: canonical append-only manager project evidence, if needed.
- Source projects and native stores: everything else, at the original roots.
""",
    }
    for name, content in files.items():
        atomic_text(workspace / name, content)
    for name in ("strategy", "portfolio", "projects", "reference", "people", "meetings"):
        with directory_fd(workspace / name, create=True):
            pass
        atomic_text(workspace / name / ".gitkeep", "")
    source_tools = Path(__file__).absolute().parent
    tools = [(name, workspace / "tools" / name) for name in (
        "workspace_manager.py", "routing_io.py", "native_ai.py",
    )]
    tools.append(("append_frame.py", workspace / "rapp-projects" / "tools" / "append_frame.py"))
    for source, destination in tools:
        with directory_fd(destination.parent, create=True):
            pass
        atomic_text(destination, read_bytes(source_tools / source).decode("utf-8"))
    registry = {
        "schema": REGISTRY_SCHEMA, "manager_rappid": rappid, "world_id": args.world_id,
        "generated_utc": utc_now(), "scan_roots": [], "workspaces": [],
        "providers": {}, "forgotten": [], "editor_view": "estate.code-workspace",
        "editor_views": ["estate.code-workspace"],
    }
    save_registry(workspace, identity, registry)
    print(f"INITIALIZED {workspace}\n{rappid}")


def empty_provider():
    return {
        "profileRoots": [], "requestedRoots": [], "catalog": [], "selected": [],
        "forgotten": [], "status": "never", "error": None, "last_attempt_utc": None,
        "last_success_utc": None, "pending": None, "observations": [],
        "profileIdentities": {}, "profileHistory": [],
    }


def validate_ids(values, provider):
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise RoutingError("selection-schema-mismatch")
    if len(values) != len(set(values)) or len(values) > Limits.CEILINGS["max_entries"]:
        raise RoutingError("selection-schema-mismatch")
    for value in values:
        if (
            not value.startswith(provider + ":") or len(value.split(":", 1)[1]) != 64
            or any(c not in "0123456789abcdef" for c in value.split(":", 1)[1])
        ):
            raise RoutingError("selection-schema-mismatch")


def validate_registry(registry):
    if set(registry) != {
        "schema", "manager_rappid", "world_id", "generated_utc", "scan_roots",
        "workspaces", "providers", "forgotten", "editor_view", "editor_views",
    } or registry["schema"] != REGISTRY_SCHEMA:
        raise RoutingError("registry-schema-mismatch")
    if (
        not isinstance(registry["workspaces"], list) or len(registry["workspaces"]) > 200000
        or not isinstance(registry["providers"], dict) or not isinstance(registry["scan_roots"], list)
    ):
        raise RoutingError("registry-schema-mismatch")
    for field in ("manager_rappid", "world_id", "generated_utc"):
        native_ai.text(registry[field])
    for root in registry["scan_roots"]:
        if native_path(root) is None:
            raise RoutingError("registry-schema-mismatch")
    ids = set()
    for item in registry["workspaces"]:
        version = item.get("pointer_version") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or type(version) is not int or version not in (1, 2)
            or set(item) != (LOCAL_FIELDS - ({"filesystemIdentity"} if version == 1 else set()))
            or item["pointer_type"] != "local-directory"
            or native_path(item["path"]) is None
            or version == 2 and item["path"] != str(absolute_path(item["path"]))
            or item["selection"] not in ("exact", "discovered")
            or item["kind"] not in ("git", "directory", "rapp-workspace")
            or item["mode"] not in (None, "solo", "hive") or item["pointer_id"] in ids
        ):
            raise RoutingError("pointer-schema-mismatch")
        expected = legacy_local_id(item["path"]) if version == 1 else local_pointer_id(item["filesystemIdentity"])
        if item["pointer_id"] != expected:
            raise RoutingError("pointer-identity-mismatch")
        for field in ("name", "rappid", "world_id"):
            native_ai.text(item[field], optional=field != "name")
        if not isinstance(item["tags"], list) or len(item["tags"]) > 32:
            raise RoutingError("pointer-schema-mismatch")
        for tag in item["tags"]:
            native_ai.text(tag)
        ids.add(item["pointer_id"])
    forgotten_ids = validate_local_suppressions(registry["forgotten"])
    if ids & forgotten_ids:
        raise RoutingError("suppressed-pointer-active")
    for provider, state in registry["providers"].items():
        if provider not in native_ai.PROVIDERS or not isinstance(state, dict) or set(state) != PROVIDER_FIELDS:
            raise RoutingError("provider-schema-mismatch")
        for field in ("profileRoots", "requestedRoots"):
            if not isinstance(state[field], list) or len(state[field]) > 16:
                raise RoutingError("provider-schema-mismatch")
            if any(native_path(root) is None for root in state[field]):
                raise RoutingError("provider-schema-mismatch")
        if not isinstance(state["profileIdentities"], dict) or set(state["profileIdentities"]) - set(state["profileRoots"]):
            raise RoutingError("provider-schema-mismatch")
        for value in state["profileIdentities"].values():
            validate_filesystem_identity(value)
        if not isinstance(state["profileHistory"], list) or len(state["profileHistory"]) > 64:
            raise RoutingError("profile-history-bound")
        for value in state["profileHistory"]:
            if not isinstance(value, dict) or set(value) != {"path", "identity"} or native_path(value["path"]) is None:
                raise RoutingError("provider-schema-mismatch")
            if value["identity"] is not None:
                validate_filesystem_identity(value["identity"])
        for field in ("selected", "forgotten"):
            validate_ids(state[field], provider)
        if set(state["selected"]) & set(state["forgotten"]):
            raise RoutingError("suppressed-pointer-active")
        if provider == "grokbot" and state["selected"]:
            raise RoutingError("grokbot-workspace-mapping-unavailable")
        if (
            state["status"] not in ("never", "refreshing", "fresh", "stale", "cleared")
            or not isinstance(state["catalog"], list) or len(state["catalog"]) > 200000
        ):
            raise RoutingError("provider-schema-mismatch")
        for field in ("error", "last_attempt_utc", "last_success_utc"):
            native_ai.text(state[field], optional=True)
        catalog_ids, forgotten = set(), set(state["forgotten"])
        for item in state["catalog"]:
            native_ai.validate_pointer(item)
            if (
                item["provider"] != provider or item["profileRoot"] not in state["profileRoots"]
                or item["pointer_id"] in forgotten or item["pointer_id"] in catalog_ids
            ):
                raise RoutingError("provider-partition-mismatch")
            catalog_ids.add(item["pointer_id"])
            if item["pointer_version"] == 2 and state["profileIdentities"].get(item["profileRoot"]) != item["profileIdentity"]:
                raise RoutingError("provider-partition-mismatch")
        if state["pending"] is not None and provider != "copilot":
            raise RoutingError("provider-schema-mismatch")
        native_ai.validate_pending(state["pending"], state["requestedRoots"], Limits(max_entries=200000))
        if not isinstance(state["observations"], list) or len(state["observations"]) > 16:
            raise RoutingError("provider-schema-mismatch")
        for item in state["observations"]:
            modern = isinstance(item, dict) and item.get("observation_version") == 2
            fields = {"provider", "profileRoot", "state", "mapping", "observation_id"}
            if modern:
                fields |= {"observation_version", "profileIdentity"}
            if (
                provider != "grokbot" or not isinstance(item, dict)
                or set(item) != fields
                or item["provider"] != provider or item["profileRoot"] not in state["profileRoots"]
                or item["state"] != "app-detected" or item["mapping"] != "workspace-mapping-unavailable"
                or item["observation_id"] in forgotten
                or modern and type(item["observation_version"]) is not int
            ):
                raise RoutingError("provider-schema-mismatch")
            expected = native_ai.routing_id("grokbot", item["profileIdentity"], "app-observation", None) if modern else native_ai.legacy_pointer_id(
                "grokbot", item["profileRoot"], "app-observation", None
            )
            if item["observation_id"] != expected or modern and state["profileIdentities"].get(item["profileRoot"]) != item["profileIdentity"]:
                raise RoutingError("provider-partition-mismatch")
    editor_name(registry["editor_view"])
    views = registry["editor_views"]
    if (
        not isinstance(views, list) or not 0 < len(views) <= 16
        or any(not isinstance(name, str) for name in views)
        or len(set(views)) != len(views) or registry["editor_view"] not in views
    ):
        raise RoutingError("editor-view-schema-mismatch")
    for name in views:
        editor_name(name)


def load_registry(workspace):
    identity = manager_identity(workspace)
    registry = read_json(absolute_path(workspace) / "registry.json", max_bytes=MAX_REGISTRY_BYTES)
    if not isinstance(registry, dict) or registry.get("schema") != REGISTRY_SCHEMA:
        raise RoutingError("registry-schema-mismatch")
    if registry.get("manager_rappid") != identity["rappid"] or registry.get("world_id") != identity["world_id"]:
        raise RoutingError("registry-identity-or-world-mismatch")
    registry.setdefault("providers", {})
    registry.setdefault("forgotten", [])
    registry.setdefault("editor_view", "estate.code-workspace")
    registry.setdefault("editor_views", [registry["editor_view"]])
    if not isinstance(registry.get("workspaces"), list):
        raise RoutingError("registry-schema-mismatch")
    for item in registry["workspaces"]:
        if not isinstance(item, dict) or "path" not in item:
            raise RoutingError("registry-schema-mismatch")
        item.setdefault("pointer_version", 1)
        item.setdefault("pointer_type", "local-directory")
        item.setdefault("pointer_id", legacy_local_id(item["path"]))
        item.setdefault("selection", "discovered")
    for state in registry["providers"].values():
        if not isinstance(state, dict):
            raise RoutingError("provider-schema-mismatch")
        state.setdefault("profileIdentities", {})
        state.setdefault("profileHistory", [])
    validate_registry(registry)
    return registry


def all_profile_roots(registry):
    return [
        root for state in registry["providers"].values()
        for root in state["profileRoots"] + state["requestedRoots"]
    ]


def all_profile_boundaries(registry):
    return [
        boundary for state in registry["providers"].values()
        for boundary in (
            [{"path": root, "identity": state["profileIdentities"].get(root)}
             for root in state["profileRoots"] + state["requestedRoots"]]
            + [{**value, "historical": True} for value in state["profileHistory"]]
        )
    ]


def native_address(item):
    if "observation_id" in item:
        return "app-observation", None, item["observation_id"]
    kind = item["pointer_type"]
    if kind == "copilot-session":
        identity = item["nativeSessionId"]
    elif kind == "claude-project":
        identity = item["nativeKey"]
    elif kind.startswith("hermes-"):
        identity = [item["nativeTable"], item["nativeId"]]
    else:
        identity = item["workspaceId"]
    return kind, identity, item["pointer_id"]


def remap_native_identities(state, result):
    """Carry selection/suppression across proven aliases and v1 key upgrades."""
    original_selected = frozenset(state["selected"])
    original_forgotten = frozenset(state["forgotten"])
    history = list(state["profileHistory"])
    history.extend({
        "path": root, "identity": state["profileIdentities"].get(root),
    } for root in state["profileRoots"])
    history.extend({
        "path": root, "identity": result["profileIdentities"][root],
    } for root in result["profileRoots"])
    unique = {json.dumps(value, sort_keys=True): value for value in history}
    history = [unique[key] for key in sorted(unique)]
    if len(history) > 64:
        raise RoutingError("profile-history-bound")
    recorded_identities = {}
    for value in history:
        if value["identity"] is not None:
            recorded_identities.setdefault(str(absolute_path(value["path"])), set()).add(tuple(value["identity"]))
    aliases, ambiguous_legacy = {}, {}
    for root in result["profileRoots"]:
        current_identity = result["profileIdentities"][root]
        at_location = {}
        for value in history:
            if value["path"] not in at_location:
                try:
                    at_location[value["path"]] = same_location(value["path"], root)
                except RoutingError:
                    at_location[value["path"]] = False
        conflicting_location = any(
            value["identity"] is not None and value["identity"] != current_identity
            and at_location[value["path"]] for value in history
        )
        equivalents, uncertain = set(), set()
        for value in history:
            same_object = value["identity"] == current_identity
            legacy_location = value["identity"] is None and at_location[value["path"]]
            conflict = (
                len(recorded_identities.get(str(absolute_path(value["path"])), set())) > 1
                or conflicting_location and at_location[value["path"]]
            )
            if conflict and (same_object or at_location[value["path"]]):
                uncertain.add(value["path"])
            elif same_object or legacy_location:
                equivalents.add(value["path"])
        aliases[root], ambiguous_legacy[root] = equivalents, uncertain
    plan, claims, ambiguous_sources = [], {}, set()
    for item in result["catalog"] + result["observations"]:
        kind, identity, key = native_address(item)
        # A v2 alias already has this exact filesystem-bound key. Never add a
        # different saved inode's key merely because its old spelling matches.
        keys = {key}
        keys.update(
            native_ai.legacy_pointer_id(result["provider"], path, kind, identity)
            for path in aliases[item["profileRoot"]]
        )
        ambiguous = {
            native_ai.legacy_pointer_id(result["provider"], path, kind, identity)
            for path in ambiguous_legacy[item["profileRoot"]]
        }
        ambiguous_sources.update(ambiguous & original_forgotten)
        suppressed_sources = frozenset(keys & original_forgotten)
        selected_sources = frozenset(keys & original_selected)
        for source in suppressed_sources | selected_sources:
            prior_target = claims.setdefault(source, key)
            if prior_target != key:
                ambiguous_sources.add(source)
        if suppressed_sources or selected_sources:
            plan.append((key, suppressed_sources, selected_sources))

    # No candidate may consume evidence needed by a later candidate's check.
    # Validate the complete plan against the original immutable sets first.
    if ambiguous_sources:
        raise RoutingError("native-identity-ambiguous")

    removed_suppressions, removed_selections = set(), set()
    suppressed_targets, selected_targets = set(), set()
    for key, suppressed_sources, selected_sources in plan:
        removed_suppressions.update(suppressed_sources)
        removed_selections.update(selected_sources)
        if suppressed_sources:
            suppressed_targets.add(key)
        if selected_sources:
            selected_targets.add(key)
    forgotten = (set(original_forgotten) - removed_suppressions) | suppressed_targets
    selected = ((set(original_selected) - removed_selections) | selected_targets) - forgotten
    return sorted(selected), forgotten, history


def check_route_boundary(workspace, path, registry):
    workspace, path = absolute_path(workspace), absolute_path(path)
    if directories_overlap(path, workspace):
        raise RoutingError("manager-route-overlap")
    if protected_local(path, all_profile_boundaries(registry)):
        raise RoutingError("native-store-not-workspace")


def validate_local_suppressions(values):
    if not isinstance(values, list) or len(values) > 200000:
        raise RoutingError("selection-schema-mismatch")
    ids = []
    for value in values:
        if isinstance(value, str):
            validate_ids([value], "local")
            ids.append(value)
        else:
            if (
                not isinstance(value, dict) or set(value) != {"pointer_id", "path", "filesystemIdentity"}
                or native_path(value["path"]) is None
                or value["pointer_id"] != local_pointer_id(value["filesystemIdentity"])
            ):
                raise RoutingError("selection-schema-mismatch")
            ids.append(value["pointer_id"])
    if len(ids) != len(set(ids)):
        raise RoutingError("selection-schema-mismatch")
    return set(ids)


def matches_local(value, path, identity=None):
    if isinstance(value, str):
        return value == legacy_local_id(str(path))
    if identity is not None and value.get("filesystemIdentity") == identity:
        return True
    return same_location(value["path"], path)


def local_suppressed(registry, path, identity):
    if any(isinstance(value, str) for value in registry["forgotten"]):
        raise RoutingError("legacy-suppression-readd-required")
    return any(matches_local(value, path, identity) for value in registry["forgotten"])


def editor_name(value):
    if (
        not isinstance(value, str) or Path(value).name != value
        or not value.endswith(".code-workspace") or value.startswith(".")
        or "/" in value or "\\" in value or len(value) > 180
        or any(ord(c) < 32 for c in value)
    ):
        raise RoutingError("editor-output-must-be-manager-owned")
    return value


def parse_editor(raw):
    """Parse VS Code JSONC; comments/formatting are not authority, settings are."""
    result, index, quoted, escaped = [], 0, False, False
    while index < len(raw):
        char = raw[index]
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            result.append(char)
        elif raw[index:index + 2] == "//":
            end = raw.find("\n", index)
            index = len(raw) if end < 0 else end
            result.append("\n")
            continue
        elif raw[index:index + 2] == "/*":
            end = raw.find("*/", index + 2)
            if end < 0:
                raise RoutingError("malformed-editor-view")
            index = end + 2
            result.append(" ")
            continue
        else:
            result.append(char)
        index += 1
    cleaned = "".join(result)
    result, quoted, escaped = [], False, False
    for index, char in enumerate(cleaned):
        if not quoted and char == ",":
            following = index + 1
            while following < len(cleaned) and cleaned[following].isspace():
                following += 1
            if following < len(cleaned) and cleaned[following] in "}]":
                continue
        result.append(char)
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
    try:
        value = json.loads(
            "".join(result), object_pairs_hook=unique_object, parse_constant=reject_constant
        )
    except (ValueError, RecursionError):
        raise RoutingError("malformed-editor-view") from None
    if not isinstance(value, dict):
        raise RoutingError("malformed-editor-view")
    return value


def editor_folders(workspace, registry):
    workspace = absolute_path(workspace)
    folders = [{"name": "RAPP Workspace Manager", "path": str(workspace)}]
    seen, profiles = {tuple(directory_identity(workspace))}, all_profile_boundaries(registry)
    budget = Budget(Limits(max_entries=200000))

    def add(name, candidate, expected_identity=None):
        budget.check()
        info = verified_directory_info(candidate, profiles, expected_identity)
        if info is not None and tuple(info["identity"]) not in seen:
            if len(folders) >= 10000:
                raise RoutingError("editor-folder-count-bound")
            check_route_boundary(workspace, info["path"], registry)
            folders.append({"name": name, "path": info["path"]})
            seen.add(tuple(info["identity"]))

    for item in registry["workspaces"]:
        budget.entry()
        add(item["name"], item["path"], item.get("filesystemIdentity"))
    for provider, state in sorted(registry["providers"].items()):
        selected = set(state["selected"])
        for item in sorted(state["catalog"], key=lambda item: item["pointer_id"]):
            if item["pointer_id"] in selected:
                budget.entry()
                for local in native_ai.local_paths(item, profiles):
                    add(f"{provider} / {native_ai.describe(item)} / {Path(local).name}", local)
    budget.check()
    return folders


def editor_projection(workspace, registry, filename=None, folders=None):
    workspace = absolute_path(workspace)
    path = workspace / editor_name(filename or registry["editor_view"])
    info = safe_stat(path, missing_ok=True)
    try:
        view = parse_editor(read_bytes(path, max_bytes=8 * 1024 * 1024).decode("utf-8")) if info else {}
    except UnicodeError:
        raise RoutingError("malformed-editor-view") from None
    if folders is None:
        folders = editor_folders(workspace, registry)
    view["folders"] = folders
    return path, view


def save_registry(workspace, identity, registry):
    workspace = absolute_path(workspace)
    stored_identity = manager_identity(workspace)
    if stored_identity["rappid"] != identity["rappid"] or stored_identity["world_id"] != identity["world_id"]:
        raise RoutingError("registry-identity-or-world-mismatch")
    validate_registry(registry)
    if registry["manager_rappid"] != identity["rappid"] or registry["world_id"] != identity["world_id"]:
        raise RoutingError("registry-identity-or-world-mismatch")
    for name in ["registry.json", "HOME.md", *registry["editor_views"]]:
        ensure_output(workspace / name)
    folders = editor_folders(workspace, registry)
    views = [editor_projection(workspace, registry, name, folders) for name in registry["editor_views"]]
    encoded = json.dumps(registry, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > MAX_REGISTRY_BYTES:
        raise RoutingError("registry-size-bound")
    # Registry first; a crash can leave a stale projection, never competing authority.
    atomic_text(workspace / "registry.json", encoded)
    write_home(workspace, identity, registry)
    for view_path, view in views:
        atomic_json(view_path, view)


def scan_manager(args):
    workspace = absolute_path(args.workspace)
    identity = manager_identity(workspace)
    rapp = load_rapp(find_rapp1(args.rapp1_path))
    if not rapp.rappid_valid(identity["rappid"]):
        raise RoutingError("manager-rappid-invalid")
    roots = list(dict.fromkeys(str(absolute_path(root)) for root in args.root))
    if len(roots) > 128:
        raise RoutingError("root-count-bound")
    exact, budget = getattr(args, "mode", "recursive") == "exact", Budget(cli_limits(args))
    with manager_lock(workspace):
        registry = load_registry(workspace)
        boundaries = all_profile_boundaries(registry)
        profile_ids = []
        for boundary in boundaries:
            budget.check()
            saved, current = resolve_protected_boundary(boundary)
            if saved is not None:
                profile_ids.append(saved)
            if current is not None and current["identity"] is not None:
                profile_ids.append(current["identity"])
        for root in map(Path, roots):
            budget.check()
            info = directory_info(root)
            if any(value in info["ancestors"] for value in profile_ids):
                raise RoutingError("native-store-not-workspace")
        paths = list(map(Path, roots)) if exact else sorted({
            path for root in roots
            for path in discover_git_workspaces(root, budget, exclude=(workspace, *boundaries))
        }, key=str)
        entries, seen = [], set()
        manager_fs_identity = directory_identity(workspace)
        for path in paths:
            budget.check()
            filesystem_id = directory_identity(path)
            key = tuple(filesystem_id)
            if filesystem_id == manager_fs_identity or key in seen:
                continue
            seen.add(key)
            check_route_boundary(workspace, path, registry)
            if not local_suppressed(registry, path, filesystem_id):
                entries.append(read_workspace_pointer(path, rapp, exact=exact, budget=budget))
        if exact:
            registry["workspaces"] = entries
        else:
            retained = [item for item in registry["workspaces"] if item["selection"] == "exact"]
            registry["workspaces"] = retained + [
                item for item in entries
                if not any(matches_local(existing, item["path"], item["filesystemIdentity"]) for existing in retained)
            ]
        registry.update(scan_roots=roots, generated_utc=utc_now())
        save_registry(workspace, identity, registry)
    print(f"SCANNED {len(entries)} {'exact' if exact else 'Git'} pointers; native selections unchanged")


def refresh_provider(workspace, provider, profile_roots=None, limits=None):
    workspace = absolute_path(workspace)
    identity = manager_identity(workspace)
    if provider not in native_ai.PROVIDERS:
        raise RoutingError("unknown-provider")
    preflight = load_registry(workspace)["providers"].get(provider, empty_provider())
    preflight_roots = profile_roots if profile_roots is not None else (
        preflight["requestedRoots"] or preflight["profileRoots"]
    )
    if len(preflight_roots) > 16:
        raise RoutingError("profile-count-bound")
    for root in preflight_roots:
        if directories_overlap(root, workspace):
            raise RoutingError("manager-native-overlap")
    with manager_lock(workspace):
        registry = load_registry(workspace)
        previous = registry["providers"].get(provider, empty_provider())
        state = copy.deepcopy(previous)
        supplied = profile_roots if profile_roots is not None else (state["requestedRoots"] or state["profileRoots"])
        if len(supplied) > 16:
            raise RoutingError("profile-count-bound")
        roots = sorted({str(absolute_path(root)) for root in supplied})
        for root in map(Path, roots):
            if directories_overlap(root, workspace):
                raise RoutingError("manager-native-overlap")
            for item in registry["workspaces"]:
                local = Path(item["path"])
                if directories_overlap(root, local):
                    raise RoutingError("native-root-overlaps-local-route")
        if roots != state["requestedRoots"]:
            state["pending"] = None
        state.update(requestedRoots=roots, last_attempt_utc=utc_now(), error=None)
        try:
            result = native_ai.scan_provider(
                provider, roots, previous=state["catalog"], pending=state["pending"], limits=limits,
            )
            if result["complete"]:
                selected, forgotten, history = remap_native_identities(state, result)
                state.update(
                    profileRoots=result["profileRoots"], requestedRoots=result["profileRoots"],
                    profileIdentities=result["profileIdentities"], profileHistory=history,
                    selected=selected, forgotten=sorted(forgotten),
                    catalog=[item for item in result["catalog"] if item["pointer_id"] not in forgotten],
                    observations=[item for item in result["observations"] if item["observation_id"] not in forgotten],
                    pending=None,
                    status="fresh", last_success_utc=utc_now(),
                )
            else:
                state.update(status="refreshing", pending=result["pending"], requestedRoots=result["profileRoots"])
        except RoutingError as error:
            state.update(status="stale", error=error.code, pending=None)
            result = {"examined": 0, "reused": 0}
        registry["providers"][provider] = state
        registry["generated_utc"] = utc_now()
        try:
            save_registry(workspace, identity, registry)
        except RoutingError as error:
            if error.code != "registry-size-bound":
                raise
            state = copy.deepcopy(previous)
            state.update(
                status="stale", error=error.code, pending=None,
                requestedRoots=roots, last_attempt_utc=utc_now(),
            )
            registry["providers"][provider] = state
            save_registry(workspace, identity, registry)
    return {
        "provider": provider, "status": state["status"], "error": state["error"],
        "candidates": len(state["catalog"]), "selected": len(state["selected"]),
        "observations": len(state["observations"]),
        "staged": len(state["pending"]["catalog"]) if state["pending"] else 0,
        "examined": result["examined"], "reused": result["reused"],
    }


def provider_action(workspace, provider, action, pointer_id=None):
    workspace = absolute_path(workspace)
    identity = manager_identity(workspace)
    if provider not in native_ai.PROVIDERS:
        raise RoutingError("unknown-provider")
    with manager_lock(workspace):
        registry = load_registry(workspace)
        state = registry["providers"].setdefault(provider, empty_provider())
        catalog = {item["pointer_id"]: item for item in state["catalog"]}
        observations = {item["observation_id"]: item for item in state["observations"]}
        if pointer_id is not None:
            validate_ids([pointer_id], provider)
        if action in ("select", "re-add"):
            if pointer_id is None:
                raise RoutingError("pointer-required")
            if action == "select" and (pointer_id not in catalog or pointer_id in state["forgotten"]):
                raise RoutingError("candidate-not-available")
            if action == "re-add" and pointer_id not in catalog and pointer_id not in state["forgotten"] and pointer_id not in observations:
                raise RoutingError("unknown-pointer")
            state["forgotten"] = [key for key in state["forgotten"] if key != pointer_id]
            if provider != "grokbot":
                state["selected"] = sorted(set(state["selected"]) | {pointer_id})
        elif action in ("clear", "clear-cache", "forget"):
            targets = {pointer_id} if pointer_id else set(catalog) | set(state["selected"]) | set(observations)
            if pointer_id and pointer_id not in catalog and pointer_id not in state["selected"] and pointer_id not in observations:
                raise RoutingError("unknown-pointer")
            state["catalog"] = [item for item in state["catalog"] if item["pointer_id"] not in targets]
            state["observations"] = [item for item in state["observations"] if item["observation_id"] not in targets]
            state["selected"] = [key for key in state["selected"] if key not in targets]
            if action == "forget":
                state["forgotten"] = sorted(set(state["forgotten"]) | targets)
            state["pending"] = None
            if pointer_id is None:
                state.update(observations=[], status="cleared", error=None)
        else:
            raise RoutingError("unknown-provider-action")
        registry["generated_utc"] = utc_now()
        save_registry(workspace, identity, registry)
    return state


def local_action(args):
    workspace, path = absolute_path(args.workspace), absolute_path(args.path)
    identity = manager_identity(workspace)
    with manager_lock(workspace):
        registry = load_registry(workspace)
        info = directory_info(path, missing_ok=True)
        filesystem_id = info["identity"]
        matches = [item for item in registry["workspaces"] if matches_local(item, path, filesystem_id)]
        if args.command == "re-add":
            check_route_boundary(workspace, path, registry)
            legacy = [value for value in registry["forgotten"] if isinstance(value, str)]
            requested_legacy = legacy_requested_ids(args.path)
            if legacy and not requested_legacy.intersection(legacy):
                raise RoutingError("legacy-suppression-readd-required")
            rapp = load_rapp(find_rapp1(args.rapp1_path))
            item = read_workspace_pointer(path, rapp, exact=True)
            registry["forgotten"] = [
                value for value in registry["forgotten"]
                if not (
                    isinstance(value, str) and value in requested_legacy
                    or not isinstance(value, str) and matches_local(value, path, item["filesystemIdentity"])
                )
            ]
            registry["workspaces"] = [value for value in registry["workspaces"] if value not in matches] + [item]
        else:
            if not matches:
                raise RoutingError("unknown-pointer")
            registry["workspaces"] = [item for item in registry["workspaces"] if item not in matches]
            if args.command == "forget":
                for item in matches:
                    saved_identity = item.get("filesystemIdentity") or filesystem_id
                    if saved_identity is None:
                        tombstone = item["pointer_id"]
                    else:
                        tombstone = {
                            "pointer_id": local_pointer_id(saved_identity),
                            "path": str(absolute_path(item["path"])), "filesystemIdentity": saved_identity,
                        }
                    key = tombstone if isinstance(tombstone, str) else tombstone["pointer_id"]
                    if key not in validate_local_suppressions(registry["forgotten"]):
                        registry["forgotten"].append(tombstone)
        registry["generated_utc"] = utc_now()
        save_registry(workspace, identity, registry)
    print(f"{args.command.upper()} manager pointer only")


def editor_manager(args):
    workspace = absolute_path(args.workspace)
    identity = manager_identity(workspace)
    with manager_lock(workspace):
        registry = load_registry(workspace)
        if args.output:
            output = Path(args.output)
            if output.is_absolute():
                if not same_directory(absolute_path(output).parent, workspace):
                    raise RoutingError("editor-output-must-be-manager-owned")
                output = output.name
            registry["editor_view"] = editor_name(str(output))
            registry["editor_views"] = sorted(set(registry["editor_views"]) | {registry["editor_view"]})
        save_registry(workspace, identity, registry)
    print(workspace / registry["editor_view"])


def list_manager(args):
    for entry in load_registry(args.workspace)["workspaces"]:
        marker = {"rapp-workspace": "rapp", "git": "git ", "directory": "dir "}[entry["kind"]]
        print(f"{marker}  {entry['name']:<36} {entry['path']}")


def open_manager(args):
    registry = load_registry(args.workspace)
    matches = [item for item in registry["workspaces"] if item["name"].casefold() == args.name.casefold()]
    if not matches:
        raise RoutingError("workspace-not-registered")
    if len(matches) > 1:
        raise RoutingError("workspace-name-ambiguous")
    path = verified_directory(
        matches[0]["path"], all_profile_boundaries(registry), matches[0].get("filesystemIdentity")
    )
    if path is None:
        raise RoutingError("local-route-unavailable")
    check_route_boundary(args.workspace, path, registry)
    if args.print_path:
        print(path)
        return
    system = platform.system()
    command = ["open", path] if system == "Darwin" else ["xdg-open", path]
    if system == "Windows":
        os.startfile(path)
    elif shutil.which(command[0]):
        subprocess.run(command, check=True)
    else:
        raise SystemExit(f"no folder opener available; path is {path}")
    print(f"OPENED {path}")


def cli_limits(args):
    return Limits(**{key: getattr(args, key) for key in Limits.DEFAULTS if hasattr(args, key)})


def provider_manager(args):
    action = args.provider_command
    if action == "inspect":
        result = native_ai.scan_provider(args.provider, args.profile_root, limits=cli_limits(args))
        pending = result.pop("pending", None)
        if pending is not None:
            result["preview"] = pending["catalog"]
    elif action == "refresh":
        result = refresh_provider(args.workspace, args.provider, args.profile_root, cli_limits(args))
    elif action == "list":
        state = load_registry(args.workspace)["providers"].get(args.provider, empty_provider())
        result = {key: value for key, value in state.items() if key != "pending"}
    else:
        state = provider_action(args.workspace, args.provider, action, args.pointer)
        result = {
            "provider": args.provider, "action": action, "candidates": len(state["catalog"]),
            "observations": len(state["observations"]),
            "selected": len(state["selected"]), "forgotten": len(state["forgotten"]),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(action == "refresh" and result["status"] == "stale")


def add_limits(command):
    for name, default in Limits.DEFAULTS.items():
        command.add_argument("--" + name.replace("_", "-"), type=float if name == "max_seconds" else int, default=default)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create an empty private pointer-only manager")
    init.add_argument("--workspace", required=True)
    init.add_argument("--owner", required=True)
    init.add_argument("--slug", default="local-workspaces")
    init.add_argument("--world-id", default="local-workspace-routing")
    init.add_argument("--rapp1-path")
    init.set_defaults(run=init_manager)
    scan = sub.add_parser("scan", help="discover Git pointers or select exact roots")
    scan.add_argument("--workspace", required=True)
    scan.add_argument("--root", action="append", required=True)
    scan.add_argument("--rapp1-path")
    scan.add_argument("--mode", choices=("recursive", "exact"), default="recursive")
    add_limits(scan)
    scan.set_defaults(run=scan_manager)
    estate = sub.add_parser("estate", help="select exactly these roots, including non-Git directories")
    estate.add_argument("--workspace", required=True)
    estate.add_argument("--root", action="append", required=True)
    estate.add_argument("--rapp1-path")
    add_limits(estate)
    estate.set_defaults(run=scan_manager, mode="exact")
    listing = sub.add_parser("list", help="list registered local pointers")
    listing.add_argument("--workspace", required=True)
    listing.set_defaults(run=list_manager)
    opener = sub.add_parser("open", help="open one unique local route")
    opener.add_argument("--workspace", required=True)
    opener.add_argument("--name", required=True)
    opener.add_argument("--print-path", action="store_true")
    opener.set_defaults(run=open_manager)
    for action in ("clear", "clear-cache", "forget", "re-add"):
        local = sub.add_parser(action, help="change only a manager-owned local pointer")
        local.add_argument("--workspace", required=True)
        local.add_argument("--path", required=True)
        if action == "re-add":
            local.add_argument("--rapp1-path")
        local.set_defaults(run=local_action)
    editor = sub.add_parser("editor-view", help="generate the deterministic manager-first projection")
    editor.add_argument("--workspace", required=True)
    editor.add_argument("--output", help="a .code-workspace filename inside the private manager")
    editor.set_defaults(run=editor_manager)
    provider = sub.add_parser("provider", help="inspect native metadata and manage selected pointers")
    actions = provider.add_subparsers(dest="provider_command", required=True)
    for action in ("inspect", "refresh", "list", "select", "clear", "clear-cache", "forget", "re-add"):
        command = actions.add_parser(action)
        command.add_argument("--provider", choices=native_ai.PROVIDERS, required=True)
        if action != "inspect":
            command.add_argument("--workspace", required=True)
        if action in ("inspect", "refresh"):
            command.add_argument("--profile-root", action="append", required=action == "inspect")
            add_limits(command)
        if action in ("select", "clear", "clear-cache", "forget", "re-add"):
            command.add_argument("--pointer", required=action in ("select", "re-add"))
        command.set_defaults(run=provider_manager)
    return root


if __name__ == "__main__":
    try:
        args = parser().parse_args()
        sys.exit(args.run(args) or 0)
    except RoutingError as error:
        print(f"REFUSED: {error.code}", file=sys.stderr)
        sys.exit(1)
