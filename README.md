# RAPP Workspace Manager

[![CI](https://github.com/kody-w/rapp-workspace-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/kody-w/rapp-workspace-manager/actions/workflows/ci.yml)

## Frame Anything — RAPP Workspace/1 Grail

**RAPP-valid != accurately observed != semantically faithful != currently
authorized != safely deployable.**

Frame an explicitly authorized finite fixture, try the canonical bounded lens,
retain refusals/exhaust, and stage a deterministic **inert captured-data view**.
An external local controller—not a candidate, lens, receipt, or projection—must
approve adoption against the complete current frontier. Deployment and unproven
learned semantics stay **disabled**.

The unique protocol ID is **`rapp-workspace/grail-1.0`**. Historical experimental
`1.0`/`1.1` identifiers are not reused. RAPP/1's eleven-key envelope is unchanged.
This is an integration of the public **candidate**, not signed Grail activation.

### One-command public synthetic demo

Supply the two explicit public checkouts; no home search, network discovery,
native profile, credential, or routed source is used:

```bash
python3 -B tools/workspace_manager.py grail demo \
  --protocol-checkout "<EXPLICIT_GRAIL_CANDIDATE_CHECKOUT>" \
  --rapp1-path "<EXPLICIT_PINNED_RAPP1_CHECKOUT>"
```

Two radically different shapes (nested arrays and binary octets) demonstrate
**lens A refusal → retained exhaust → lens B success**. B actually reads the
refusal/exhaust context, with inherited restrictions. A third shape produces a
stable refusal. Each result prints all five scoped assurance receipts; even an
adopted view has **safe deployment refused**. This is deterministic bounded
mapping, not evidence of learned native semantics.

The default output is the fresh manager-owned
`.validation/grail-manager-demo`; an existing seed is never reset. The report
contains no real input paths. JSON, escaped Markdown, and a manager-only editor
view are inert; no source is added as an editor root.

### Existing manager: bind, preserve the seed, observe, stage

```bash
python3 -B tools/workspace_manager.py grail --help
python3 -B tools/workspace_manager.py grail contract
python3 -B tools/workspace_manager.py grail bind \
  --workspace "<EXISTING_PRIVATE_MANAGER>" \
  --protocol-checkout "<EXPLICIT_GRAIL_CANDIDATE_CHECKOUT>" \
  --rapp1-path "<EXPLICIT_PINNED_RAPP1_CHECKOUT>"
python3 -B tools/workspace_manager.py grail verify \
  --workspace "<EXISTING_PRIVATE_MANAGER>"
```

Continue with the [exact Frame Anything command sequence and scope format](docs/frame-anything.md).
Capture and retention are separate explicit flags; synthesis, adoption, and
materialization need their own grants too. The manager RAPPID, routing world,
registry schema, owner order, and suppressions are preserved.

- `.grail/` is a **closed manager-owned control sidecar**, not a replacement
  identity, task store, routing registry, or protocol.
- Jobs are bounded references to canonical observations, lenses, attempts,
  refusals, exhaust, five receipts, and externally staged decisions.
- File fixtures are stable-descriptor observations, **not coherent native
  snapshots**. Bounded directory fixtures contain one-level metadata only.
  Both remain non-adoptable, including their fallback derivatives.
- `grail migrate --metadata-only` reads the existing manager registry only.
  It never visits routed paths. V1 pointers without filesystem identity stay
  unresolved until an explicit safe re-add and a new metadata observation.
- `grail inspect|status|tree|focus` expose scoped assurances without turning
  them into authority. `grail recover` repairs disposable mirrors/projections
  from the controller's atomic ledger, never from a learned adoption claim.

Public redistribution, native grafts/rebinding, live behavior-preserving
migration, hosted models, arbitrary code/imports, coherent database snapshots,
partitioned/external effects, timed erasure, and learned-capability claims are
explicit refusals. Private shadow/live-pilot blockers are in the
[handoff checklist](docs/frame-anything.md#private-shadow-and-live-pilot-blockers).

## Existing pointer-only routing (backward compatible)

The original private routing manager for independent workspaces and native
AI workspace metadata remains available. It is the **first editor root, not a container**.

- `registry.json` owns routing selection and suppression only.
- `HOME.md` and `.code-workspace` files are disposable projections.
- Source projects retain their files, Git history, identity, worlds and RAPP/1
  frames. Native providers retain their own storage models and authority.
- Discovery is **not** selection. A native session catalog never automatically
  becomes a list of editor roots.
- Clear/forget never delete, disconnect, close, move or edit anything native.

There is no new estate protocol, common AI session store, transcript index,
copied project content, or competing task system.

For autonomous end-to-end setup, migration, grouping, testing, and maintenance,
use [`.github/skills/autonomous-rapp-estate-manager/SKILL.md`](.github/skills/autonomous-rapp-estate-manager/SKILL.md).
It composes this manager with RAPP Workspace and RAPP/1 while preserving the
pointer-only boundary.

## Requirements and privacy

Python 3.10+ for legacy routing (3.11+ for Grail), no third-party Python packages, and a local canonical
[`rapp-1`](https://github.com/kody-w/rapp-1) checkout for initialization and RAPP
identity validation. Safe filesystem operations currently require POSIX
descriptor-relative no-follow I/O and locking (macOS/Linux). Unsupported
platforms fail closed rather than fall back to following links. Hermes metadata
queries additionally require SQLite 3.37+ and the OS `/dev/fd` interface.

Only explicit owner-approved roots are inspected. There is no automatic home
scan, native-store search, provider process launch, or network call. Public
fixtures and examples are synthetic. Real roots, native IDs, membership,
registries and generated editor views belong in the **private manager**, never
in this repository.

## Initialize and select the exact estate

```bash
python3 tools/workspace_manager.py init \
  --workspace ~/local-workspaces \
  --owner example \
  --rapp1-path ~/src/rapp-1

python3 ~/local-workspaces/tools/workspace_manager.py estate \
  --workspace ~/local-workspaces \
  --root ~/src/global-estate \
  --root ~/src/project-01 \
  --root ~/notes/project-02 \
  --rapp1-path ~/src/rapp-1
```

`estate` (also `scan --mode exact`) replaces the **local** selection with
exactly the supplied directories, in owner-supplied order. Non-Git directories
are valid pointers. It does not discover nested repositories. Suppressed roots
remain suppressed until `re-add`; native provider partitions are unchanged.
Supplying the manager itself is harmless: it appears exactly once, first.

The synthetic [13-root fixture](examples/estate-13.synthetic.json) demonstrates:

```text
RAPP Workspace Manager
RAPP Global Estate
Project 01
…
Project 11
```

These are independent sibling directories, not repositories copied inside the
manager. A name containing “RAPP” does not establish identity or conformance.
Only canonical validation of an allowlisted root `rappid.json` earns the
`rapp-workspace` label.

Recursive Git discovery still exists:

```bash
python3 ~/local-workspaces/tools/workspace_manager.py scan \
  --workspace ~/local-workspaces --root ~/src --rapp1-path ~/src/rapp-1
```

It replaces the Git-discovered local partition while retaining exact selections
and all native partitions. Nested Git roots and worktree `.git` **markers** are
discovered without reading `.git` contents. Home, native-store roots, symlinks,
pruned build directories and the manager subtree are not traversed.

## Local recursive organization overlay

The registry remains `schema: rapp-workspace-manager/1`. Its additive
`organization` version 1 field is a **local manager overlay**, not a new estate
protocol, identity system, task store or content index. It groups selected local
pointers without moving them or changing their `rapp-workspace` or RAPP/1
identity. The manager remains the first editor root and never becomes a
container for routed workspaces.

Legacy registries receive one empty in-memory root group (`root`, displayed as
`Estate`) when loaded; loading does not rewrite the registry or remint identity.
Groups form a bounded parent-ID tree. A selected local pointer may have one
alias and zero or one placement; no placement means **Unorganized**. Unknown
keys, versions, pointers, parents, duplicate IDs/placements, cycles and invalid
names fail closed.

```bash
python3 tools/workspace_manager.py group add \
  --workspace ~/local-workspaces --id engineering --name "Engineering"
python3 tools/workspace_manager.py group add \
  --workspace ~/local-workspaces --id services --name "Services" \
  --parent engineering
python3 tools/workspace_manager.py group assign \
  --workspace ~/local-workspaces --id services \
  --path ~/src/example-service --alias service
python3 tools/workspace_manager.py tree --workspace ~/local-workspaces
python3 tools/workspace_manager.py group unassign \
  --workspace ~/local-workspaces --path ~/src/example-service
python3 tools/workspace_manager.py group remove \
  --workspace ~/local-workspaces --id services
```

Root removal and removal of a group with children or placements are refused.
Exact and recursive rescans retain aliases and placements when the selected
pointer identity remains, and prune them when it does not. Clear/forget also
prune active organization references; re-add returns the pointer unorganized
until an explicit assignment.

`focus` creates or updates a deterministic manager-owned editor view:

```bash
python3 tools/workspace_manager.py focus \
  --workspace ~/local-workspaces --target engineering
python3 tools/workspace_manager.py focus \
  --workspace ~/local-workspaces --target service --print-path
```

A group focus contains placed local pointers in that group and all descendant
groups. A workspace focus contains only the uniquely resolved selected local
name or alias. `--print-path` is valid only for workspace targets. Focused views
are tracked with existing editor views, regenerated after routing/organization
changes, manager-first, atomic and JSON/JSONC-value preserving. The ordinary
`editor-view` remains the all-selected local/native view.

See [docs/recursive-estate-pattern.md](docs/recursive-estate-pattern.md) for a
bounded delivery and private-pilot checklist.

## Explicit native adapters

| Provider ID | Read-only metadata surface | Native identity and limitations |
|---|---|---|
| `copilot` | `PROFILE/session-state/UUID/workspace.yaml` | Profile root + native session UUID. Only `id,cwd,git_root,repository,host_type,branch,client_name,created_at,updated_at`. Non-repository, nested and worktree cwd values remain distinct. Scalar YAML only; no `data.db` fallback. |
| `claude` | `PROFILE/projects/NATIVE-KEY/sessions-index.json`, version 1 | Profile/native projects root + unchanged bucket key. Retains originalPath/projectPath associations, including multiple paths in one bucket. Missing indexes remain unresolved; keys are never reverse-decoded into paths. |
| `hermes` | `PROFILE/state.db`, gated metadata tables/columns | Native table + native project/folder/session ID. Conditional metadata columns only, not a reconstructed common project model. Missing cwd stays unknown; terminal-session breadcrumbs are not read. See the WAL limitation below. |
| `scout` | `PROFILE/m-sessions/workspaces.json`, version 3 | Native version, workspace ID, provider ID and rootId. Only `providerId: local` can yield a verified filesystem path. ODSP and other provider references remain opaque, even if rootId looks like an existing path. |
| `grokbot` | Existence of explicit `Grokbot.app`, `.grokbot` or `Grokbot` roots | `app-detected / workspace-mapping-unavailable` observation only. No durable bot→workspace mapping is claimed or inferred. No persistence files are opened. |

The [synthetic native metadata examples](examples/native/) show the supported
shapes. Schema changes are refused, not guessed.

**Hermes gate:** only `user_version = 0` and ordinary tables with a declared
`TEXT` or `INTEGER` `id` are supported. The exact table/column allowlists are in
[SPEC.md](SPEC.md#5-hermes-read-only-snapshot-gate). Tables may be absent; unknown
columns are never selected. These conditional shapes are not a claim that
every installed Hermes release has a native project/folder model.

**Hermes WAL limitation:** the adapter pins a no-follow-opened database inode,
uses `mode=ro&immutable=1`, connection-only query restrictions and a short shared
read lock. A nonempty WAL or rollback journal, busy writer, changed file, unknown
schema, or unavailable safe reader causes a stale/error result. It does **not**
ignore the WAL, open SHM for writing, checkpoint the provider, or copy a database
containing chats. Retry after the native owner has made the store quiescent.
Active-WAL live ingestion is intentionally unavailable.

Hermes source checkouts can be selected independently with `estate`; they are
not its session store. Scout's fallback `PROFILE/workspace` is protected from
editor-root selection. Grokbot app/support/runtime/cache/skills/settings paths
are never workspaces. An owner can select a real project directory separately;
a future documented native export would need its own reviewed adapter.

## Inspect, refresh, select

These commands use explicit profile roots; none of the examples run
automatically:

```bash
python3 tools/workspace_manager.py provider inspect \
  --provider copilot --profile-root ~/.copilot --batch-size 250

python3 tools/workspace_manager.py provider refresh \
  --workspace ~/local-workspaces --provider copilot \
  --profile-root ~/.copilot --batch-size 1000

python3 tools/workspace_manager.py provider list \
  --workspace ~/local-workspaces --provider copilot

python3 tools/workspace_manager.py provider select \
  --workspace ~/local-workspaces --provider copilot \
  --pointer 'copilot:HASH_FROM_PROVIDER_LIST'
```

Substitute `claude --profile-root ~/.claude`, `hermes --profile-root ~/.hermes`,
`scout --profile-root ~/.scout`, or `grokbot --profile-root /Applications/Grokbot.app`
when explicitly authorized. Repeat `--profile-root` to supply a provider's
complete approved profile set. Omitting it on later refreshes reuses the last
requested set. A failed change of profile set preserves all last-good pointers.

`inspect` writes nothing. An incomplete inspection returns a bounded preview,
not active routes. `list` reads the private registry only.

Copilot refresh inventories **one level of directory names**, then parses at
most `--batch-size` session metadata files per invocation. Repeat refresh until
`status: fresh`; manager-owned `pending` metadata checkpoints resume the work.
Unchanged file fingerprints reuse prior metadata without reopening YAML files.
Directory membership changes invalidate staging and require a retry.

A complete successful scan replaces **only that provider partition**. Until
then, the old catalog and owner selections remain active. Errors discard
incomplete staging, set `status: stale` plus a content-free error code, and keep
the last successful catalog and timestamp. CLI refresh exits nonzero on stale
errors; `refreshing` is successful bounded progress, not a completed scan.

## Clear-cache versus forget

```bash
# Remove known manager pointers/caches and selections. Refresh may rediscover.
python3 tools/workspace_manager.py provider clear-cache \
  --workspace ~/local-workspaces --provider copilot

# Remove and durably suppress one native identity.
python3 tools/workspace_manager.py provider forget \
  --workspace ~/local-workspaces --provider copilot \
  --pointer 'copilot:HASH_FROM_PROVIDER_LIST'

# Explicitly lift suppression and select the identity on its next rediscovery.
python3 tools/workspace_manager.py provider re-add \
  --workspace ~/local-workspaces --provider copilot \
  --pointer 'copilot:HASH_FROM_PROVIDER_LIST'
python3 tools/workspace_manager.py provider refresh \
  --workspace ~/local-workspaces --provider copilot

# Local pointers use their exact paths, including non-Git roots.
python3 tools/workspace_manager.py forget \
  --workspace ~/local-workspaces --path ~/notes/project-02
python3 tools/workspace_manager.py re-add \
  --workspace ~/local-workspaces --path ~/notes/project-02 \
  --rapp1-path ~/src/rapp-1
```

`clear` and `clear-cache` are aliases. For providers, omit `--pointer` to clear
the whole known catalog; `forget` without a pointer suppresses all **currently
known** IDs, not future unknown identities. Native suppression keeps opaque
identifiers; local suppression keeps an identifier, original location and
filesystem identity so aliases, renames and directory replacement cannot undo
forget. Clear-cache does not remove tombstones. Re-add does not create a
session, infer a path or touch the native store. Rediscovered candidates are
unselected unless the owner explicitly selected/re-added their IDs.

All these operations rebuild manager-owned projections. A shared filesystem
root remains visible if another selected pointer still references it.

Grokbot observations have manager-owned `observation_id` keys for the same
clear/forget/re-add lifecycle (pass the key with `--pointer`). These keys
identify observations only, not bots or workspaces. Re-add lifts observation
suppression on the next refresh; `select` still refuses a workspace mapping.

## Editor and dashboard projections

```bash
python3 tools/workspace_manager.py editor-view --workspace ~/local-workspaces
python3 tools/workspace_manager.py list --workspace ~/local-workspaces
python3 tools/workspace_manager.py open \
  --workspace ~/local-workspaces --name project-01 --print-path
```

The default is `estate.code-workspace` **inside the private manager**. Optional
`--output selected.code-workspace` must also stay inside that directory. The
registry tracks generated view filenames so clear/forget also update older
manager-generated views. Up to sixteen views are supported.

Generation is deterministic, manager-first, deduplicated by device/inode identity,
and atomic per file. It preserves unrelated JSON/JSONC settings, extensions and
other top-level values; comments/formatting may be rewritten. Invalid existing
editor files fail closed. Only selected, existing, no-follow local directories
become folders. Missing, unresolved, protected and nonlocal provider roots
remain in the dashboard/catalog, never fabricated filesystem paths.

`open` operates on unique local pointer names or organization aliases.
Ambiguous names/aliases and unavailable paths are refused. With no
`--print-path`, it prefers `code -n <path>` when the VS Code CLI is available,
then retains the platform folder-opener fallback. It never invokes a provider
lifecycle API.
The dashboard caps its native preview at 100 candidates per provider.

## Filesystem identity and legacy cache safety

Pointer version 2 retains native shapes and adds no-follow filesystem identity:
`filesystemIdentity: [device, inode]` on local pointers and `profileIdentity`
on native pointers. Grokbot observations use the same profile identity and
`observation_version: 2`. Display paths are locators, not identity.

Leading slash aliases normalize to one ordinary `/` root. Home (including its
ancestors), manager and registered native-profile boundaries use pinned
directory identities and kernel parent links, not lexical path prefixes.
Case aliases collapse only when the filesystem resolves them to the same
device/inode; distinct names on case-sensitive volumes stay distinct.
Symlink traversal and multiply-linked metadata/output/lock files are refused.
Local projections also verify the saved identity, so replacing a directory at
the same spelling does not silently retarget a selected pointer.

Legacy v1 metadata stays readable, but Copilot v1 caches and checkpoints are
untrusted for routing until a complete refresh through the structural reader.
Multiline quoted values, flow collections, aliases, tags, unsupported indentation
or document forms fail closed even under ignored keys. Ignored indented block
scalars remain opaque; their continuation text never becomes metadata.

Provider namespace history (bounded to 64 entries per provider) preserves
suppression and selection while v1 keys upgrade and profile aliases change.
Different saved device/inode identities are never aliases, even at the same
spelling: their original suppressions remain intact and selection requires
explicit re-add. Ambiguous v1 suppression stays stale with
`native-identity-ambiguous` rather than being guessed or discarded.
Migration planning checks the complete candidate/observation set against
immutable original selection and suppression sets before applying changes.
Competing target claims are refused, and catalog ordering cannot consume a
tombstone before another candidate proves it ambiguous.
Cached Copilot metadata is rebound to the current verified locator without
changing its stable pointer identity. Historical protection follows remembered
objects through verified current locators; inaccessible, symlinked or reused
obsolete names cannot hide unrelated healthy routes.

Old local identifier-only tombstones lack recoverable filesystem provenance:
new local scans fail closed with `legacy-suppression-readd-required` until
explicit re-add using the original recorded path spelling. Unrecoverable or
unsafe old locations require owner review of **manager metadata only**, never
native-data deletion or automatic tombstone loss.

## Bounds and exclusions

Default scan limits (CLI-overridable only up to fixed ceilings):

| Bound | Default | Hard ceiling |
|---|---:|---:|
| Enumerated entries / metadata rows | 150,000 | 200,000 |
| Copilot metadata records per invocation | 1,000 | 10,000 |
| Single metadata file | 2 MiB | 8 MiB |
| Metadata bytes per invocation | 16 MiB | 64 MiB |
| Cooperative scan deadline | 10 seconds | 60 seconds |

There are also fixed caps: 16 native profile roots, 128 exact/recursive scan
roots, recursion depth 64, 128 kernel ancestry steps, 64 saved namespaces per
provider, 4 KiB metadata strings, 128 MiB compact metadata per
provider catalog/stage, 512 MiB manager registry, 8 MiB existing editor files,
64 KiB local RAPP identity files, 512 organization groups, 10,000 aliases,
10,000 placements, and 2 GiB Hermes database file size (not a database-copy
budget). Editor projection allows 10,000 folders, with a
10-second cooperative directory-verification deadline. No directory inventory
is recursive for native stores.

Bounds include ignored directory entries. File reads are bounded and stable
across before/after stat checks. Time limits are cooperative: Python cannot
preempt an individual stalled filesystem/OS call. Batched file observations
are not an instantaneous transactional snapshot of an active native store.

Never opened: Copilot events/session DB/files/checkpoints/research/rewind/
summaries/todos/search, Claude transcripts/memory/history/plans/instructions/
attachments, Hermes messages/titles/previews/prompts/config blobs/memory or
terminal pane content, Scout sessions/browser/auth, or Grokbot persistence.
Only root RAPP identity metadata is read from selected source projects.

## RAPP/1 authority and verification

This is the existing `rapp-workspace-manager/1` profile with a closed versioned
**pointer union**, not a new wire protocol or identity system. Pointer hashes
are local routing keys, not RAPPIDs, signatures or acceptance evidence.
Source-owned RAPP/1 frames remain at their source; views do not confer compliance.
Structural verification is not authenticated acceptance, authorization,
publication or deployment. No owner signatures are inferred.

The repository's existing project stream is checked without inventing a new
estate event. Where project history is required, the bundled canonical writer
uses existing `body.pulse` / `work.status`, never a new estate protocol.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 -m py_compile tools/*.py
python3 /path/to/rapp-1/rapp_check.py . --json
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_conformance.py . \
  --rapp1-path /path/to/rapp-1
```

Tests use only repository-local synthetic fixtures, native/source read canaries,
before/after native byte-and-metadata snapshots, an actual SQLite WAL and busy
writer, 257 filesystem-backed Copilot sessions, and a virtual 99,000-name
inventory. They do not access live native profiles. Conformance evidence must
include scanned **existing frames**, not a zero-artifact pass.

Some canonical `rapp_check.py` revisions only discover numeric frame filenames
and skip this repository's sequence-plus-hash filenames. `check_conformance.py`
combines that unchanged canonical checker with the existing writer's canonical
`verify_chain`, counts verified source frames, and fails on zero-frame evidence.
It does not rename, copy or rewrite frames. CI uses this combined check rather
than treating an identity-only linter verdict as full frame conformance.

The future Workspaces Librarian interaction remains agent-first: explain the
organization, inspect approved metadata, propose bounded pointer changes, and
apply owner-selected routes. The UI is a passive projection, not another
control plane.

See [SPEC.md](SPEC.md) for the checkable contract and Python API.

Public tool identity:
`rappid:@kody-w/rapp-workspace-manager:98439b87ffb132681bf9bbaa50c65f01bb29373a38ffd17c310119a05d9f5ee5`.

MIT licensed.
