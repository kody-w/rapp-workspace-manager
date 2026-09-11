#!/usr/bin/env python3
"""Create and operate a pointer-only local RAPP Workspace manager."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REGISTRY_SCHEMA = "rapp-workspace-manager/1"
PRUNED_DIRS = {
    ".cache",
    ".git",
    ".next",
    ".parcel-cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def find_rapp1(explicit=None):
    candidates = [
        explicit,
        os.environ.get("RAPP1_PATH"),
        "~/Documents/GitHub/rapp-1",
        "~/rapp-1",
        "~/src/rapp-1",
    ]
    for candidate in candidates:
        if candidate and (Path(candidate).expanduser() / "rapp.py").is_file():
            return Path(candidate).expanduser().resolve()
    raise SystemExit("rapp.py not found; pass --rapp1-path or set RAPP1_PATH")


def load_rapp(rapp1_path):
    sys.path.insert(0, str(rapp1_path))
    import rapp

    return rapp


def manager_identity(workspace):
    identity_path = Path(workspace) / "rappid.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"not a manager workspace: missing {identity_path}")
    if (
        identity.get("schema") != "rapp/1"
        or identity.get("kind") != "workspace"
        or identity.get("role") != "manager"
    ):
        raise SystemExit(f"not a RAPP Workspace manager: {identity_path}")
    return identity


def discover_git_workspaces(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"scan root is not a directory: {root}")

    found = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in PRUNED_DIRS)
        current_path = Path(current)
        if ".git" in files or (current_path / ".git").is_dir():
            found.append(current_path.resolve())
    return sorted(set(found), key=lambda path: str(path).casefold())


def read_workspace_pointer(path, rapp_module):
    pointer = {
        "name": path.name,
        "path": str(path),
        "kind": "git",
        "mode": None,
        "world_id": None,
        "rappid": None,
        "tags": [],
    }
    identity_path = path / "rappid.json"
    if identity_path.is_symlink() or not identity_path.is_file():
        return pointer

    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return pointer

    rappid = identity.get("rappid")
    tags = identity.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        tags = []
    if (
        identity.get("schema") == "rapp/1"
        and identity.get("kind") == "workspace"
        and rapp_module.rappid_valid(rappid)
    ):
        pointer.update(
            {
                "kind": "rapp-workspace",
                "mode": identity.get("mode") if identity.get("mode") in ("solo", "hive") else None,
                "world_id": (
                    identity.get("world_id")
                    if isinstance(identity.get("world_id"), str)
                    else None
                ),
                "rappid": rappid,
                "tags": tags,
            }
        )
    return pointer


def render_home(identity, registry):
    entries = registry["workspaces"]
    rapp_count = sum(entry["kind"] == "rapp-workspace" for entry in entries)
    rows = []
    for entry in entries:
        tags = ", ".join(entry["tags"]) if entry["tags"] else "-"
        rows.append(
            f"| {entry['name']} | {entry['kind']} | {entry['mode'] or '-'} | "
            f"`{entry['path']}` | {tags} |"
        )
    table = "\n".join(rows) if rows else "| _No workspaces found_ | - | - | - | - |"
    return f"""# Local Workspace Manager

**PRIVATE / NEVER PUBLISH.** This dashboard contains pointers only. It must
never absorb files or content from the workspaces it routes.

- Manager: `{identity["rappid"]}`
- World: `{identity["world_id"]}`
- Last scan: `{registry["generated_utc"]}`
- Registered paths: **{len(entries)}**
- RAPP Workspaces: **{rapp_count}**

## Workspaces

| Name | Kind | Mode | Local path | Tags |
| --- | --- | --- | --- | --- |
{table}

## Commands

```bash
python3 tools/workspace_manager.py scan --workspace . --root ~/Documents/GitHub
python3 tools/workspace_manager.py list --workspace .
python3 tools/workspace_manager.py open --workspace . --name <workspace-name>
```

`registry.json` is the routing authority for this manager. It stores metadata
and local paths only; source files remain inside their own world boundaries.
"""


def write_home(workspace, identity, registry):
    path = Path(workspace) / "HOME.md"
    path.write_text(render_home(identity, registry), encoding="utf-8", newline="\n")


def init_manager(args):
    workspace = Path(args.workspace).expanduser().resolve()
    identity_path = workspace / "rappid.json"
    if identity_path.exists():
        raise SystemExit(f"refusing to re-mint existing identity: {identity_path}")

    rapp = load_rapp(find_rapp1(args.rapp1_path))
    workspace.mkdir(parents=True, exist_ok=True)
    rappid = rapp.mint_rappid(args.owner, args.slug)
    if not rapp.rappid_valid(rappid):
        raise SystemExit("minted rappid failed validation")

    identity = {
        "schema": "rapp/1",
        "rappid": rappid,
        "kind": "workspace",
        "role": "manager",
        "name": args.slug,
        "mode": "solo",
        "world_id": args.world_id,
    }
    atomic_json(identity_path, identity)

    files = {
        "README.md": """# PRIVATE / NEVER PUBLISH

This is a local RAPP Workspace manager. It contains pointers to local
workspaces, never their content. Do not publish, mirror, or attach a public
remote. The owner remains sovereign over every outward or irreversible action.
""",
        "CLAUDE.md": """# Manager operating contract

This workspace routes the owner to local workspaces. Read `registry.json` and
`HOME.md`; do not read routed workspace content merely to populate this
manager. Preserve every `world_id` boundary. Store pointers and identity
metadata only. Ask before deleting, moving, publishing, or adding remotes.
""",
        "OWNER.md": """# Owner

The local owner is sovereign. Keep identifying and personal details outside
this manager unless they are required for routing.
""",
        "where-everything-lives.md": """# Where everything lives

- `registry.json` — pointer-only routing authority.
- `HOME.md` — generated dashboard projection.
- `rappid.json` — mint-once RAPP identity.
- `rapp-projects/` — append-only RAPP/1 project frame authority.
- Routed workspace content — remains at each registered local path.
""",
    }
    for relative, content in files.items():
        (workspace / relative).write_text(content, encoding="utf-8", newline="\n")
    for directory in ("strategy", "portfolio", "projects", "reference", "people", "meetings"):
        (workspace / directory).mkdir(exist_ok=True)
        (workspace / directory / ".gitkeep").touch()

    source_tools = Path(__file__).resolve().parent
    (workspace / "tools").mkdir(exist_ok=True)
    shutil.copy2(source_tools / "workspace_manager.py", workspace / "tools" / "workspace_manager.py")
    (workspace / "rapp-projects" / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        source_tools / "append_frame.py",
        workspace / "rapp-projects" / "tools" / "append_frame.py",
    )

    registry = {
        "schema": REGISTRY_SCHEMA,
        "manager_rappid": rappid,
        "world_id": args.world_id,
        "generated_utc": utc_now(),
        "scan_roots": [],
        "workspaces": [],
    }
    atomic_json(workspace / "registry.json", registry)
    write_home(workspace, identity, registry)
    print(f"INITIALIZED {workspace}")
    print(rappid)


def scan_manager(args):
    workspace = Path(args.workspace).expanduser().resolve()
    identity = manager_identity(workspace)
    rapp = load_rapp(find_rapp1(args.rapp1_path))
    if not rapp.rappid_valid(identity.get("rappid")):
        raise SystemExit("manager rappid failed canonical RAPP/1 validation")
    roots = sorted({str(Path(root).expanduser().resolve()) for root in args.root})
    paths = set()
    for root in roots:
        paths.update(discover_git_workspaces(root))
    paths.discard(workspace)
    entries = [read_workspace_pointer(path, rapp) for path in sorted(paths, key=str)]
    registry = {
        "schema": REGISTRY_SCHEMA,
        "manager_rappid": identity["rappid"],
        "world_id": identity["world_id"],
        "generated_utc": utc_now(),
        "scan_roots": roots,
        "workspaces": entries,
    }
    atomic_json(workspace / "registry.json", registry)
    write_home(workspace, identity, registry)
    print(f"SCANNED {len(entries)} workspaces into {workspace / 'registry.json'}")


def load_registry(workspace):
    identity = manager_identity(workspace)
    path = Path(workspace).expanduser().resolve() / "registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"missing registry: {path}")
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"unsupported registry schema in {path}")
    if registry.get("manager_rappid") != identity["rappid"]:
        raise SystemExit(f"registry identity mismatch in {path}")
    if registry.get("world_id") != identity["world_id"]:
        raise SystemExit(f"registry world boundary mismatch in {path}")
    return registry


def list_manager(args):
    entries = load_registry(args.workspace)["workspaces"]
    for entry in entries:
        marker = "rapp" if entry["kind"] == "rapp-workspace" else "git "
        print(f"{marker}  {entry['name']:<36} {entry['path']}")


def open_manager(args):
    entries = load_registry(args.workspace)["workspaces"]
    matches = [entry for entry in entries if entry["name"].casefold() == args.name.casefold()]
    if not matches:
        raise SystemExit(f"workspace not registered: {args.name}")
    if len(matches) > 1:
        paths = "\n".join(f"- {entry['path']}" for entry in matches)
        raise SystemExit(f"workspace name is ambiguous; use a unique name:\n{paths}")

    path = matches[0]["path"]
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


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a private pointer-only manager workspace")
    init.add_argument("--workspace", required=True)
    init.add_argument("--owner", required=True)
    init.add_argument("--slug", default="local-workspaces")
    init.add_argument("--world-id", default="local-workspace-routing")
    init.add_argument("--rapp1-path")
    init.set_defaults(run=init_manager)

    scan = sub.add_parser("scan", help="replace the registry from local Git roots")
    scan.add_argument("--workspace", required=True)
    scan.add_argument("--root", action="append", required=True)
    scan.add_argument("--rapp1-path")
    scan.set_defaults(run=scan_manager)

    listing = sub.add_parser("list", help="list registered workspace pointers")
    listing.add_argument("--workspace", required=True)
    listing.set_defaults(run=list_manager)

    opener = sub.add_parser("open", help="open one registered workspace locally")
    opener.add_argument("--workspace", required=True)
    opener.add_argument("--name", required=True)
    opener.add_argument("--print-path", action="store_true")
    opener.set_defaults(run=open_manager)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    args.run(args)
