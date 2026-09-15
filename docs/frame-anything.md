# Frame Anything: RAPP Workspace/1 manager

**RAPP-valid != accurately observed != semantically faithful != currently
authorized != safely deployable.**

This is a local core-protocol integration, not a native migration,
deployment service, learned-capability claim, or signed activation. Existing
`rapp-workspace-manager/1` routing remains backward compatible. The Workspace/1
sidecar never replaces the manager RAPPID, registry, source worlds, or tasks.
Its protocol ID is uniquely `rapp-workspace/1`; RAPP/1 is unchanged.

## Explicit pins and authorization

Run all commands from this public manager implementation. Replace every quoted
placeholder with an explicit, approved absolute path. None of these commands
discovers a checkout, reads a native profile, launches a provider, or fetches
anything over the network.

```bash
python3 -B tools/workspace_manager.py workspace1 contract
python3 -B tools/workspace_manager.py workspace1 bind \
  --workspace "<EXISTING_PRIVATE_MANAGER>" \
  --protocol-checkout "<EXPLICIT_RAPP_WORKSPACE1_CHECKOUT>" \
  --rapp1-path "<EXPLICIT_PINNED_RAPP1_CHECKOUT>"
python3 -B tools/workspace_manager.py workspace1 verify \
  --workspace "<EXISTING_PRIVATE_MANAGER>"
```

The expected spec, manifest, and RAPP/1 commit are compiled into
`tools/workspace1_runtime.py`, not selected by a received manifest. `bind` verifies
every exact manifest entry, the unique index selection, schema/runtime
membership, provenance and canonical parent bytes. It retains public bytes in
one inert `runtime-image.json`, not importable files or generated instructions.
The loader compiles the same captured verified module bytes and consumes
captured validator schemas/provenance. The only evaluator is the
canonical no-import total evaluator. Every fresh execution requalifies the
current complete closure; an old pass, different bytecode, plugin, or receipt
is no substitute.

Binding requires an existing valid private manager, matching registry
identity/world, a `PRIVATE / NEVER PUBLISH` guard, safe no-follow POSIX I/O,
locking, private controller ownership and Python 3.11+. A changed checkout
inode, missing controller, changed pins, or attempted rebinding refuses.
A pre-existing manager-root `frames` location also refuses: starting another
sequence-zero chain under the same identity is not a safe migration. Existing
separate project streams are left alone. An owner must establish that there
is no other independently located root stream; this host does not search for
or graft one.

## Initialize exactly one seed

Declare scopes before use, from independent host policy—not from a source,
lens or received receipt. The scope list is bounded and closed. An example is
[`examples/workspace1/scopes.synthetic.json`](../examples/workspace1/scopes.synthetic.json):

```json
[
  {
    "subject": {"namespace": "synthetic", "native_key": "document"},
    "form": "supplied-octets",
    "path": null
  }
]
```

For `file-octets` or `directory-metadata-fixture`, `path` must be the **exact
approved absolute fixture path**. Scope registration performs no fixture I/O.
`manager-seed:root` and `manager-registry:routing` are reserved local controller
scopes. Namespace/native-key pairs are provenance bindings, not minted native
identities or new RAPPIDs.

```bash
python3 -B tools/workspace_manager.py workspace1 init \
  --workspace "<EXISTING_PRIVATE_MANAGER>" \
  --scopes-file "<ABSOLUTE_HOST_SELECTED_SCOPES_JSON>" \
  --expires-utc "2027-01-01T00:00:00.000Z" \
  --allow-capture --allow-retention --allow-local-synthesis \
  --allow-adoption --allow-materialization
```

Grant only the rights needed; each flag is independent. Retention is required
to retain the seed. Choose an actual authorized expiry, not an arbitrary
evergreen timestamp. Live commands use trusted host UTC and a durable clock
floor. Captured timestamps never establish current permission.

An exact repeated `init` preserves the seed and every root counter. Changing
scope, rights, expiry or budgets is **not** a reinitialization workaround:
the core protocol refuses it pending a separately reviewed policy transition.
Deleting a state cache cannot remint the seed. A missing authoritative store
is a recovery blocker, not an empty manager.

Defaults are 8 attempts, depth 4, 256 frames and 1 MiB aggregate capture.
Hard ceilings are 128 attempts, depth 32, 512 frames and 64 MiB aggregate
capture. Each immutable observation is at most 64 KiB. The root reserves stop
capacity; renamed jobs, children, fanout and retries cannot reset counters.
At most 32 jobs/scopes and 32 stage operations are tracked.

## Capture only the declared form

Supplied octets have no source path. This example supplies `[1,[2,3]]`:

```bash
python3 -B tools/workspace_manager.py workspace1 capture \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job document \
  --subject synthetic:document --form supplied-octets \
  --octets-base64 WzEsWzIsM11d --allow-capture --allow-retention
```

For a file scope declared during initialization:

```bash
python3 -B tools/workspace_manager.py workspace1 capture \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job file-fixture \
  --subject synthetic:document --form file-octets \
  --fixture "<EXACT_APPROVED_FIXTURE_FILE>" --synthetic-fixture \
  --allow-capture --allow-retention
```

For a declared one-level directory metadata fixture:

```bash
python3 -B tools/workspace_manager.py workspace1 capture \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job directory-fixture \
  --subject synthetic:document --form directory-metadata-fixture \
  --fixture "<EXACT_APPROVED_FIXTURE_DIRECTORY>" --max-entries 64 \
  --synthetic-fixture --allow-capture --allow-retention
```

These are alternate scope declarations, not permission to change a scope's
form on use. Missing flags, denied/expired policy, exhausted pre-access budgets
or undeclared scope refuse **before fixture stat, enumeration, open or decode**.
Links, hardlinks, special files, credential/native names, protected native
locations and controller/tooling overlap refuse. Never point fixture scopes at
real credentials or native profiles, even if renamed. A fixture attestation
is owner-supplied scope, not a classifier capable of finding every secret.

File buffers are `stable-descriptor-not-coherent`. Directory fixtures enumerate
at most 128 immediate names/types/file sizes within a ten-second cooperative
bound; no child contents or descendants are read. Their assembled immutable
buffer explicitly says `one-level-metadata-not-coherent`. Directory/live
native capture remains unqualified: **file and directory fixture descendants
inherit adoption denial**, so feedback cannot launder them into native-backed
adoption. No coherent database/live-profile snapshot is claimed. Deadlines
cannot preempt a stalled OS syscall.

Invalid UTF-8, duplicate JSON names and large integer tokens may be retained
opaquely; strict interpretation can refuse. No iterators, cyclic object
capture, ambient environment, host tools, arbitrary program, or model call
is accepted.

## Run the canonical safe lens loop

```bash
python3 -B tools/workspace_manager.py workspace1 run \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job document \
  --strategy adaptive --field workspace \
  --allow-local-synthesis --allow-retention --allow-capture
```

`adaptive` first tries exact `json-field` lens A. A failed interpretation and
its repeated-state exhaust are retained. Lens B receives a new immutable
context containing the original bytes, A's refusal and exhaust, intersecting
all inherited restrictions. B runs canonical `identity-octets`: its actual,
necessary and synthesis reads include that context. It does not learn a
native schema. Feedback capture needs its own capture right; insufficient
feedback budget/rights preserves A's evidence and records a stop.

`--strategy identity` directly requests byte identity.
`--strategy strict-field` retains a stable refusal without fallback.
Exact retries reuse a job's immutable plan and result. A changed plan needs a
new explicit job, still under the same root budget. Neither success nor replay
establishes fidelity; selected-field coverage cannot claim full behavior.

## External staging and adoption transaction

```bash
python3 -B tools/workspace_manager.py workspace1 stage \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job document \
  --operation-id accept-document --approve-identity-contract \
  --allow-local-synthesis --allow-retention
```

`stage` externally selects the exact complete captured-octet identity/inverse
contract, checks it through the canonical verifier and emits an inert request.
It returns a **token** binding the request, full protocol frontier, exact
manager registry/identity bytes, routing/order/organization/worlds,
suppression set, external policy and binding. It changes no routing or
adopted head.

The independently controlling caller must pass that exact token and a
separate action grant:

```bash
python3 -B tools/workspace_manager.py workspace1 adopt \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --operation-id accept-document \
  --expected-frontier "<EXACT_TOKEN_FROM_STAGE>" \
  --allow-adoption --allow-retention
```

The existing manager lock and canonical controller lock serialize one local
writer. Canonical adoption, receipts, decision ledger, heads, manager job/stage
state and checkpoint commit in **one SQLite transaction**. SQLite COMMIT is
the linearization point. Nested operations use savepoints. All manager
frontier components are rechecked before commit. Interrupted transactions
roll back together; lost acknowledgements return the same committed record.
Manager stage decisions must exactly correspond to the canonical adoption
ledger. Lost/inconsistent decision metadata is quarantined, never reconstructed
as authority from a cache or learned graph.
A changed operation or stale source/policy/graph/routing/suppression/runtime/
world/manager frontier refuses. Retrying a committed acknowledgement is
history, not a renewed materialization grant.

No candidate/lens can invoke the controller. Graph reconstruction never
reconstructs rights. Forks latch refusal; no unsigned local fault is called
signed owner equivocation. Whole-store rollback still needs an independently
protected checkpoint—an owned store cannot authenticate its own rollback.

## Inert status, projections, focus and recovery

```bash
python3 -B tools/workspace_manager.py workspace1 status --workspace "<EXISTING_PRIVATE_MANAGER>"
python3 -B tools/workspace_manager.py workspace1 inspect --workspace "<EXISTING_PRIVATE_MANAGER>" --job document
python3 -B tools/workspace_manager.py workspace1 tree --workspace "<EXISTING_PRIVATE_MANAGER>"
python3 -B tools/workspace_manager.py workspace1 project \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --allow-materialization --allow-retention
python3 -B tools/workspace_manager.py workspace1 focus \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job document \
  --allow-materialization --allow-retention
python3 -B tools/workspace_manager.py workspace1 recover \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --allow-materialization --allow-retention
python3 -B tools/workspace_manager.py workspace1 history \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --allow-retention
```

`tree` is a JSON seed/job/assurance tree, never a source traversal.
`focus` filters one job's assurance metadata, including safe refusals; captured
byte values still require adoption. The editor contains the manager once and
**no native/source roots**. Outputs are fixed `.workspace1/view.json`,
`.workspace1/view.md`, and `.workspace1/estate.code-workspace`. Existing registry/editor
views and their settings are not changed. Raw source text remains encoded
data, never Markdown instructions, HTML, remote images/links, terminal
controls, task definitions, executable files or extension recommendations.

Projection checksums/focus are committed before individually atomic output
writes. A crash may leave stale disposable files; `status` exposes checksum
and frontier staleness, and `recover` regenerates them from the controller.
Without `--allow-materialization`, `recover --allow-retention` only repairs the
state cache. Changed registry/suppression frontiers block stale projection
materialization. A newly observed/adopted job may be explicitly focused to
exclude stale historical adoptions without resetting the seed. The default
all-job projection still refuses if any included adoption is stale. Views
never become an authority fallback.

Five receipts retain their subject, scope, method, validator/runtime pin and
status. `current_authorization` is an action snapshot, never a reusable grant.
`history` can verify nonzero parent frames using retained pinned public bytes
when the fresh evaluator is unavailable; the other assurances remain scoped
historical/unavailable. It still requires current retention rights and time.
History does not authorize execution, scope renewal, native rebinding, export
or deployment.

## Registry-metadata-only migration

```bash
python3 -B tools/workspace_manager.py workspace1 migrate \
  --workspace "<EXISTING_PRIVATE_MANAGER>" --job registry-observation \
  --metadata-only --allow-capture --allow-retention
```

Only existing manager-registry metadata is captured: original registry bytes,
normalized legacy defaults, pointer/native IDs, order, worlds, suppression and
organization. No routed path, native profile or source content is opened,
statted or rebound. The observation is bounded to 64 KiB; oversized or
incomplete coverage refuses rather than silently truncating a migration.

V1 pointers without filesystem identity, unresolved selected native IDs and
incomplete native partitions remain unresolved and non-adoptable. Migration
does not silently upgrade them. An independently approved legacy `re-add`
may verify an exact local fixture/root; a **new** registry-metadata observation
is then required. The old observation remains unresolved evidence.

Even complete V2 metadata permits only an inert captured-metadata projection:
it is **not** a behavior-preserving/native migration. A changed legacy
frontier cannot be repaired by merely staging a fresh approval of old capture.
Registry identity/world/order/suppression and all routed sources stay unchanged.

## Reproducible public validation

Use the explicit core checkout, never a convenient prototype validator:

```bash
export RAPP_WORKSPACE1_CHECKOUT="<EXPLICIT_RAPP_WORKSPACE1_CHECKOUT>"
export RAPP1_PATH="<EXPLICIT_PINNED_RAPP1_CHECKOUT>"
python3 -B -m unittest discover -s tests -p 'test_workspace1_manager.py' -v
python3 -B -m unittest discover -s tests -v
python3 -m py_compile tools/*.py tests/*.py
python3 -B tools/check_conformance.py . --rapp1-path "$RAPP1_PATH"
python3 -B tools/check_workspace1_conformance.py \
  --protocol-checkout "$RAPP_WORKSPACE1_CHECKOUT" --rapp1-path "$RAPP1_PATH"
```

The integration tests do not discover dependencies; without both explicit
environment paths that class is skipped, **not** Workspace/1 acceptance. An
acceptance run must have zero skipped integration/canonical gates. The
cross-repo checker copies only exact manifest-listed public/synthetic bytes
and the public index into a fresh owned validation mirror, runs the core
conformance there, requires nonzero frames, and compares core bytes
before/after. It never writes into the supplied checkout.
The mirror's literal public documentation is validation input, not a manager
materialization. The withdrawn experimental suite is not acceptance.

The targeted manager suite and canonical safety matrix cover authority,
pre-access rights, inherited restrictions, complete-frontier transactions,
process death/recovery/idempotence, fidelity/domain/coherence, source occurrence
versus subject suppression, merge/context/read coverage, root budgets/cycles,
historical runtime, delta freshness, single-writer/fork, metadata migration,
inert output, executable closure and portability.

## Private shadow and live pilot blockers

Public conformance is **not authorization** for either.

Before a private metadata shadow: independently approve the exact existing
manager/backup/shadow/tooling roots, identity/world, metadata scope, capture and
retention policy, expiry, private ownership and single-writer interval. Back up
only allowlisted manager-owned data, preserving newer suppression and
checkpoints. Rehearse controller/projection recovery and inspect v1/unresolved
or oversized frontiers. No private shadow is created by these public tests.

Before any live native pilot: independent owner approval, qualified coherent
snapshot and behavior/mapping coverage, safe explicit subject/path rebinding,
protected monotonic checkpoint/key custody, private rights/retention handling,
and separate production/runtime qualification are still missing gates.
Hosted model calls, arbitrary execution, source grafts, live behavior-preserving
migration, coherent database snapshots, partitioned effects, external
deployment, public export and general learned-semantic claims remain disabled
in this implementation. Signed profile activation/publication are separate
owner actions, not consequences of passing tests.
