# RAPP Workspace Manager Profile

`spec_id: rapp-workspace-manager/1`

This profile defines a pointer-only manager for local workspaces. It is an
application of `rapp/1` identity and frames plus the workspace-manager rule in
`rapp-workspace/1.1`.

## 1. Boundary

A manager routes among local workspaces. It MUST NOT ingest, duplicate, index,
summarize, embed, or publish routed workspace content.

## 2. Private instance

Each generated manager instance MUST:

- remain local and private by default;
- carry one mint-once `rapp/1` workspace identity;
- declare `role: manager`, `mode: solo`, and one routing `world_id`;
- keep a loud `PRIVATE / NEVER PUBLISH` guard;
- store its routing authority in `registry.json`;
- treat `HOME.md` as a generated projection of that registry.

## 3. Registry

The registry schema is `rapp-workspace-manager/1`. Each entry may contain only
pointer metadata:

- `name`;
- absolute local `path`;
- `kind`;
- verified root-level `rappid`;
- `mode`;
- `world_id`;
- routing `tags`.

The manager MUST NOT follow a symlinked `rappid.json`. It MUST use the canonical
RAPP/1 implementation to validate a discovered identity before labeling a
directory as a RAPP Workspace.

## 4. Operations

Scanning replaces the generated registry atomically. Listing and opening read
the registry but do not modify routed workspaces. Duplicate names fail closed.
The manager never deletes, moves, clones, commits, pushes, or edits a routed
workspace.

## 5. Frame authority

A generated manager carries `rapp-projects/tools/append_frame.py`. Project
history MAY be recorded as append-only RAPP/1 frame streams. Every emitted
frame MUST be built and verified by the canonical RAPP/1 reference
implementation, linked to the prior payload hash, and written atomically.

## 6. Public/private split

This public repository contains only the reusable shell and tests. Generated
registries, dashboards, local paths, identities, and owner data belong to the
private instance and MUST NOT be committed back to this repository.
