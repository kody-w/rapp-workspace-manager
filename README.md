# RAPP Workspace Manager

[![CI](https://github.com/kody-w/rapp-workspace-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/kody-w/rapp-workspace-manager/actions/workflows/ci.yml)

A private, local-first manager for all of your local Git and RAPP workspaces.
It scans folders you choose, stores a registry of pointers, generates a
Markdown dashboard, and opens a selected workspace with the local operating
system.

The manager never copies source files, notes, credentials, or workspace
content into its registry. Each routed workspace stays inside its own
`world_id` boundary.

## Requirements

- Python 3.10 or newer.
- A local checkout of [`kody-w/rapp-1`](https://github.com/kody-w/rapp-1).
- macOS, Linux, or Windows.

No Python packages are required.

## Quick start

```bash
git clone https://github.com/kody-w/rapp-1 ~/src/rapp-1
git clone https://github.com/kody-w/rapp-workspace-manager
cd rapp-workspace-manager

python3 tools/workspace_manager.py init \
  --workspace ~/RAPP-Workspace-Manager \
  --owner your-handle \
  --rapp1-path ~/src/rapp-1

python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py scan \
  --workspace ~/RAPP-Workspace-Manager \
  --root ~/Documents/GitHub \
  --rapp1-path ~/src/rapp-1
```

Open `~/RAPP-Workspace-Manager/HOME.md` for the generated dashboard.

## Manage workspaces

```bash
# Refresh from one or more roots
python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py scan \
  --workspace ~/RAPP-Workspace-Manager \
  --root ~/Documents/GitHub \
  --root ~/src \
  --rapp1-path ~/src/rapp-1

# List registered pointers
python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py list \
  --workspace ~/RAPP-Workspace-Manager

# Open a workspace in the operating system
python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py open \
  --workspace ~/RAPP-Workspace-Manager \
  --name my-project
```

Duplicate names are refused rather than guessed. Use `--print-path` to resolve
a unique workspace without opening it.

## What gets stored

`registry.json` stores only:

- local path and directory name;
- whether the path is a Git repository or a verified RAPP Workspace;
- valid root-level RAPP identity, mode, world, and tags when present;
- scan roots and generation time.

Root-level `rappid.json` symlinks and invalid identities are ignored. Routed
workspace files are never ingested.

## RAPP/1 guarantees

- The private manager gets a canonical, mint-once `rappid`.
- Registry and dashboard writes are local and atomic.
- The manager has one routing `world_id` and never merges routed content.
- Its bundled project writer builds and verifies append-only RAPP/1 frames
  through the canonical `rapp.py` implementation.
- The owner remains sovereign; the tool does not delete, move, publish, clone,
  commit, or modify a routed workspace.

See [`SPEC.md`](SPEC.md) for the checkable manager profile.

Public tool identity:
`rappid:@kody-w/rapp-workspace-manager:98439b87ffb132681bf9bbaa50c65f01bb29373a38ffd17c310119a05d9f5ee5`.

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 -m py_compile tools/workspace_manager.py tools/append_frame.py
python3 /path/to/rapp-1/rapp_check.py . --json
```

MIT licensed.
