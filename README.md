# RAPP Workspace Manager

[![CI](https://github.com/kody-w/rapp-workspace-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/kody-w/rapp-workspace-manager/actions/workflows/ci.yml)

One local estate view for independent Git and RAPP workspaces.

The manager is the first editor root, not a filesystem container. It keeps a
private registry of pointers and generates a multi-root view with every managed
project beside it. Projects stay in their original directories with their own
Git history, identity, world boundary, instructions, tests, and RAPP/1 frames.

```text
RAPP Workspace Manager
RAPP Global Estate
Copilot Builder — RAPP Work
Microsoft CEO
LLC Autofile
Private LLC Portfolio
RAPP
RAR
ambient-context
AIdeate
herdr
Copilot Harness SDK
RAPP Factory
```

This side-by-side estate is the manual proof for a larger interaction:

> Describe the organization you want. The AI inspects the actual estate,
> explains the meaningful tradeoffs, recommends a better shape, and applies
> the confirmed pointer/view mutation without moving or deleting projects.

## The boundary

The manager owns:

- selected workspace pointers;
- display names and safe routing metadata;
- a generated Markdown dashboard;
- a generated VS Code multi-root view;
- links to source-owned evidence and proposed next frames.

The manager does **not** own:

- project source, notes, credentials, frames, or artifacts;
- project identity, history, decisions, readiness, or execution;
- a second task system, registry authority, or protocol;
- physical deletion, moves, clones, commits, publication, or deployment.

**Clear removes a pointer and generated view entry only.** It never deletes or
modifies the destination. A cleared project can be re-added later with the same
source identity and history.

## Manual estate proof

The current private proof uses:

`~/rapp-work/RAPP-Work-Local-Estate.code-workspace`

It contains the manager first and twelve selected sibling roots: the default
RAPP Global Estate world plus eleven local project roots. That file is
machine-local evidence, not public registry authority. Real absolute paths and
private estate membership are not committed here.

The existing scanner remains recursive discovery. The next manager frame is an
explicit-root mode that:

1. registers exactly the directories selected by the owner;
2. includes valid non-Git workspace directories;
3. generates the manager-first multi-root view atomically;
4. preserves unrelated editor settings;
5. supports pointer-only Clear and re-add;
6. never reads or writes managed project content.

Until that frame lands, the current multi-root file is a manually assembled
proof of the desired shape.

## Audited estate: proposed next frames

These are read-only recommendations from the local September 13, 2026 audit.
They are **proposals**, not accepted work, execution authority, or claims that
every project is already RAPP/1 conformant.

| Workspace | Current frame | Proposed next frame |
|---|---|---|
| **RAPP Workspace Manager** | Pointer-first routing manager; generated dashboard is a projection. | Add exact-root registration and deterministic manager-first VS Code generation with pointer-only Clear. |
| **RAPP Global Estate** | `ESTATE_MAP.md` preserves a historical 92-repository observation; current `estate-map.json` is a derived spine projection, not authenticated registry authority. | Reconcile the historical observation with a current bounded spine refresh and publish an evidence-labeled drift brief without turning observation into owner acceptance. |
| **Copilot Builder — RAPP Work** | Active bridge worktree for operating a root bot through Copilot CLI. | Add a CI-enforced canonical bot-bridge acceptance suite covering identity, replay, restart, evidence, visibility, and zero model/guest effects for reporting. |
| **Microsoft CEO** | 105 RAPP project streams verify, but navigation projections are stale. | Close the authority-to-projection freshness loop so indexes and cockpit views derive from verified stream heads after appends. |
| **LLC Autofile** | Private local evidence filer with append-only reviewed receipts. | Separate repository-safe synthetic validation from explicitly authorized owner-local registry checks. |
| **Private LLC Portfolio** | Private governance repository with multiple venture roots and distributed verification. | Add a privacy-safe tracked repository map and drift gate without reading operational records or creating another control plane. |
| **RAPP** | Experimental restored source, structurally pinned to RAPP/1 rev-5, not fully conformant. | Make `TRUST-001` the single contributor-owned offline registry-verification work package while preserving owner-only authorization blockers. |
| **RAR** | Large single-file agent registry with publication receipts; current local checkout is behind its recorded upstream. | Make published RAPPID identity mint-once and persistent instead of deriving it from changing source hashes. |
| **ambient-context** | Push-context reference library; advertised trust guarantees have enforcement gaps. | Make registration-level `UNTRUSTED` sticky so callbacks can downgrade trust but cannot silently elevate it. |
| **AIdeate** | Local-first static workshop kit with sensitive browser state and broad checkout serving. | Replace ad hoc directory serving with a loopback-only allowlisted public-asset server and privacy gate. |
| **herdr** | Terminal execution and observation substrate, not a canonical task/evidence ledger. | Add one evidence-gated next-frame handoff record so reviewers do not depend on pane status or terminal scrollback. |
| **Copilot Harness SDK** | Useful multi-transport client with inconsistent lifecycle semantics between adapters. | Centralize session lifecycle guarantees and enforce them with one offline parameterized conformance suite across every mode. |
| **RAPP Factory** | Substantial document-to-agent implementation with incomplete readiness evidence. | Establish one maintainer-owned Review BOM separating implemented, artifact-verified, runtime-verified, and accepted states. |

## RAPP/1-first rules

The manager never makes a project compliant after the fact. Every mutation must
first identify the existing RAPP/1 primitive that expresses it.

- Canonical project frames remain authoritative at the source root.
- Registry entries are routing pointers, not copied project history.
- Dashboard and editor files are disposable projections.
- Next-frame links point to source-owned proposal evidence; the manager does not
  copy `next_action` text into a competing backlog.
- Branches and immutable history are never rewritten or flattened.
- Missing trust, identity, evidence, or authority is shown as missing.
- Structural verification is not authenticated acceptance.
- Owner-only signatures, registries, re-anchors, publication, and deployment
  are never inferred from a local green check.

Project posture must be stated honestly as one of:

- verified for the exact cited check;
- structurally aligned;
- provisional or candidate;
- not yet conformant;
- not evaluated.

## Autonomous Agent First

The future workflow is not a dashboard-first management product.

1. The user describes an organizational thought in natural language.
2. The agent inspects bounded, approved evidence.
3. It explains tradeoffs and proposes one next frame.
4. The user confirms or corrects the proposal.
5. The agent applies only the bounded pointer/projection mutation.
6. Canonical project evidence remains at its source.
7. The UI is generated later as a passive view of the proven interaction.

The manager is therefore a routing and visibility substrate for the
**Workspaces Librarian**, not another application users must administer.

## Current commands

Requirements:

- Python 3.10 or newer.
- A local checkout of [`kody-w/rapp-1`](https://github.com/kody-w/rapp-1).
- macOS, Linux, or Windows.
- No third-party Python packages.

Initialize a private manager:

```bash
python3 tools/workspace_manager.py init \
  --workspace ~/RAPP-Workspace-Manager \
  --owner your-handle \
  --rapp1-path ~/src/rapp-1
```

Discover pointers under approved roots:

```bash
python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py scan \
  --workspace ~/RAPP-Workspace-Manager \
  --root ~/Documents/GitHub \
  --root ~/Developer \
  --root ~/rapp-work \
  --rapp1-path ~/src/rapp-1
```

List or resolve a registered pointer:

```bash
python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py list \
  --workspace ~/RAPP-Workspace-Manager

python3 ~/RAPP-Workspace-Manager/tools/workspace_manager.py open \
  --workspace ~/RAPP-Workspace-Manager \
  --name my-project
```

Duplicate names are refused rather than guessed. Use `--print-path` to resolve
a unique route without opening it.

## Stored data

`registry.json` contains pointers and bounded root metadata:

- local path and directory name;
- whether the destination is a Git repository or verified RAPP workspace;
- valid root-level RAPP identity, mode, world, and tags when present;
- scan roots and generation time.

Root-level `rappid.json` symlinks and invalid identities are ignored. Routed
workspace files are never ingested.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 -m py_compile tools/workspace_manager.py tools/append_frame.py
python3 /path/to/rapp-1/rapp_check.py . --json
```

The private manager has a mint-once `rappid`. Its bundled writer builds and
verifies append-only frames through the selected canonical `rapp.py`
implementation. These checks establish only their exact stated scope.

See [`SPEC.md`](SPEC.md) for the checkable manager profile.

Public tool identity:
`rappid:@kody-w/rapp-workspace-manager:98439b87ffb132681bf9bbaa50c65f01bb29373a38ffd17c310119a05d9f5ee5`.

MIT licensed.
