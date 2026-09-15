"""Public synthetic manager integration gates; explicit protocol/parent paths only."""

import argparse
import base64
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import workspace1_manager as g
import workspace1_runtime as runtime
import workspace_manager as wm
from routing_io import RoutingError, directory_identity
from support import fixture_directory, metadata_guard, snapshot, write_json

NOW = "2026-09-15T04:30:00.000Z"
EXPIRY = "2027-01-01T00:00:00.000Z"
SUBJECT = {"namespace": "synthetic", "native_key": "input"}
CAPTURE = {"allow_capture": True, "allow_retention": True}
RUN = {"allow_local_synthesis": True, "allow_retention": True, "allow_capture": True}
STAGE = {"approve_identity_contract": True, "allow_local_synthesis": True, "allow_retention": True}
ADOPT = {"allow_adoption": True, "allow_retention": True}
PROJECT = {"allow_materialization": True, "allow_retention": True}


class Workspace1ContractUnitTests(unittest.TestCase):
    def test_unique_protocol_id_and_exact_help(self):
        expected = runtime.contract()
        self.assertEqual(expected["spec_id"], "rapp-workspace/1")
        self.assertTrue(expected["authority"])
        self.assertEqual(expected["external_effects"], "disabled")
        parser = wm.parser()
        subcommands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices
        help_text = subcommands["workspace1"].format_help()
        for command in ("bind", "verify", "init", "capture", "run", "stage", "adopt",
                        "migrate", "inspect", "status", "tree", "focus", "history", "recover"):
            self.assertIn(command, help_text)
        self.assertIn("No network discovery", " ".join(help_text.split()))

    def test_no_discovery_expansion_or_unsupported_effect_access(self):
        for value in (None, "relative", "~/candidate", "/fictional/../candidate", "//ambiguous"):
            with self.subTest(value=value), self.assertRaises(RoutingError):
                runtime.explicit_path(value)
        for operation in ("model_submission", "network", "loopback", "imports", "execution",
                          "external_deployment", "live_migration", "partitioned_effect", "public_export"):
            with self.subTest(operation=operation), mock.patch.object(g, "host", side_effect=AssertionError("access")):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(g.dispatch(argparse.Namespace(workspace1_command="effect", operation=operation)), 1)

    def test_capture_flags_precede_any_host_or_source_access(self):
        for flags in ({}, {"allow_capture": True}, {"allow_retention": True}):
            with self.subTest(flags=flags), mock.patch.object(g, "host", side_effect=AssertionError("access")):
                with self.assertRaisesRegex(RoutingError, "explicit"):
                    g.capture("/fictional/manager", "input", SUBJECT, form="file-octets",
                              path="/fictional/secret", **flags)

    def test_escaping_cannot_generate_links_images_html_or_terminal_commands(self):
        rendered = g.escaped('![x](https://example.invalid/i)<script>`\x1b[2J\n')
        for raw in ("![", "https:", "<script>", "`", "\x1b", "\n"):
            self.assertNotIn(raw, rendered)


class Workspace1ManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        protocol, parent = os.environ.get("RAPP_WORKSPACE1_CHECKOUT"), os.environ.get("RAPP1_PATH")
        if not protocol or not parent:
            raise unittest.SkipTest("explicit RAPP_WORKSPACE1_CHECKOUT and RAPP1_PATH required; no dependency discovery")
        cls.protocol, cls.parent = runtime.explicit_path(protocol), runtime.explicit_path(parent)
        cls.files = runtime.capture_checkout(cls.protocol)
        cls.image = runtime.Runtime(cls.protocol, cls.parent, cls.files)
        cls.addClassCleanup(cls.image.close)

    def setUp(self):
        self.context = fixture_directory()
        self.root = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.workspace = self.root / "manager"
        self.workspace.mkdir(mode=0o700)
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        self.source = self.fixtures / "document.fixture"
        self.source.write_bytes(b"PUBLIC SYNTHETIC INPUT")
        rid = self.image.core.r.mint_rappid("fictional", "manager-test")
        self.identity = {"schema": "rapp/1", "rappid": rid, "kind": "workspace", "role": "manager",
                         "name": "synthetic", "world_id": "routing-fixture-world", "mode": "solo"}
        write_json(self.workspace / "rappid.json", self.identity)
        (self.workspace / "README.md").write_text("# PRIVATE / NEVER PUBLISH\n")
        self.registry = {
            "schema": wm.REGISTRY_SCHEMA, "manager_rappid": rid, "world_id": self.identity["world_id"],
            "generated_utc": NOW, "workspaces": [], "scan_roots": [], "providers": {}, "forgotten": [],
            "editor_view": "estate.code-workspace", "editor_views": ["estate.code-workspace"],
            "organization": wm.default_organization(),
        }
        self.save_registry()

    def save_registry(self):
        write_json(self.workspace / "registry.json", self.registry)

    def prepare(self, *, form="supplied-octets", path=None, rights=None, checkout=None, **limits):
        g.bind(self.workspace, checkout or self.protocol, self.parent)
        self.scopes = [{"subject": SUBJECT, "form": form, "path": str(path) if path else None}]
        self.rights = set(g.RIGHTS) if rights is None else set(rights)
        g.initialize(self.workspace, self.scopes, rights=self.rights, expires_utc=EXPIRY, now=NOW, **limits)

    def capture(self, raw=b"captured synthetic bytes", job="input", **kwargs):
        return g.capture(self.workspace, job, SUBJECT, form="supplied-octets", octets=raw, now=NOW, **CAPTURE, **kwargs)

    def candidate(self, raw=b"captured synthetic bytes", job="input", strategy="identity"):
        self.capture(raw, job)
        return g.run_lenses(self.workspace, job, strategy=strategy, now=NOW, **RUN)

    def ready(self, *, job="input", operation="accept-input", raw=b"captured synthetic bytes"):
        self.candidate(raw, job)
        return g.stage(self.workspace, job, operation, now=NOW, **STAGE)

    def status(self):
        return g.inspect(self.workspace, now=NOW)

    def read_state(self):
        with g.host(self.workspace, now=NOW) as value:
            return copy.deepcopy(value.state)

    def mirror(self):
        path = self.root / "public-protocol"
        path.mkdir()
        for name, raw in self.files.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        return path

    def test_exact_contract_matches_core_spec_manifest_and_all_blocking_gate_ids(self):
        self.assertEqual(runtime.sha(self.files[runtime.PROTOCOL + "/SPEC.md"]), runtime.SPEC_SHA256)
        self.assertEqual(runtime.sha(self.files[runtime.PROTOCOL + "/manifest.json"]), runtime.MANIFEST_SHA256)
        gates = json.loads(self.files[runtime.PROTOCOL + "/safety-matrix.json"])
        ids = {row["id"] for row in gates["requirements"]}
        self.assertEqual(ids, {"VERSION", "P0-1", "P0-2", "P0-3", "P0-4", "P1-FIDELITY", "P1-DOMAIN",
                              "P1-SNAPSHOT", "P1-IDENTITY", "P1-MERGE", "P1-READS", "P1-REATTACH",
                              "P1-BUDGET", "P1-HISTORY", "P1-DELTA", "P1-EFFECTS", "P1-MIGRATION",
                              "P1-INERT", "P1-CLOSURE", "P1-PORTABILITY", "P1-LEARNING",
                              "P1-CATALOG", "P1-OUTCOME", "P1-HIVE", "P1-SCALE",
                              "P1-COMPOSE"})
        self.assertTrue(all(row["vectors"] for row in gates["requirements"]))

    def test_binding_and_init_preserve_identity_registry_world_and_one_seed(self):
        before = snapshot(self.workspace)
        self.prepare()
        seed = self.read_state()["seed_lineage"]
        again = g.initialize(self.workspace, self.scopes, rights=self.rights, expires_utc=EXPIRY, now=NOW)
        self.assertEqual(seed, [again["seed"]])
        self.assertEqual(self.status()["root_budget"]["frames_used"], 1)
        after = snapshot(self.workspace)
        for filename, record in before.items():
            self.assertEqual(record, after[filename])
        self.assertEqual(wm.load_registry(self.workspace)["schema"], wm.REGISTRY_SCHEMA)
        with self.assertRaisesRegex(RoutingError, "separate-reviewed-transition"):
            g.initialize(self.workspace, [], rights=self.rights, expires_utc=EXPIRY, now=NOW)

    def test_closed_sidecar_cannot_be_a_new_identity_task_or_authority_store(self):
        self.prepare()
        state = self.read_state()
        for key, value in (("tasks", []), ("effective_rights", ["execute"]), ("identity", self.identity)):
            mutated = {**state, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(RoutingError, "closed"):
                g.validate_state(mutated)
        for version in (True, 2, "1"):
            with self.subTest(version=version), self.assertRaisesRegex(RoutingError, "version"):
                g.validate_state({**state, "version": version})
        forged_cache = {**state, "effective_rights": ["execution"]}
        g.write_json(self.workspace / ".workspace1/state.json", forged_cache)
        self.assertTrue(self.status()["assurance_receipts_are_not_authority"])
        with g.host(self.workspace, now=NOW) as value:
            with value.c.transaction():
                value.c._put("manager_state", forged_cache)
        with self.assertRaisesRegex(RoutingError, "closed"):
            self.status()

    def test_missing_controller_cannot_remint_existing_seed(self):
        self.prepare()
        (self.workspace / ".workspace1/controller/controller.sqlite3").unlink()
        with self.assertRaisesRegex(RoutingError, "never-remints"):
            g.initialize(self.workspace, self.scopes, rights=self.rights, expires_utc=EXPIRY, now=NOW)

    def test_existing_root_stream_is_not_forked_by_reusing_manager_identity(self):
        frames = self.workspace / "frames"
        frames.mkdir()
        (frames / "0.json").write_bytes(b"existing manager-owned stream; do not reinterpret")
        with metadata_guard([frames], []), self.assertRaisesRegex(RoutingError, "root-stream-needs-qualified"):
            self.prepare()
        self.assertFalse((self.workspace / ".workspace1/controller").exists())

    def test_lost_manager_decision_metadata_is_quarantined_not_rebuilt_as_authority(self):
        self.prepare()
        prepared = self.ready()
        g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        with g.host(self.workspace, now=NOW) as value:
            altered = copy.deepcopy(value.state)
            altered["stages"]["accept-input"]["status"] = "staged"
            altered["stages"]["accept-input"]["record"] = None
            with value.c.transaction():
                value.c._put("manager_state", altered)
        with self.assertRaisesRegex(RoutingError, "decision-ledger-quarantine"):
            g.recover(self.workspace, allow_retention=True, now=NOW)

    def test_current_closure_drift_or_extra_executable_refuses_before_evaluation(self):
        checkout = self.mirror()
        self.prepare(checkout=checkout)
        evaluator = checkout / runtime.PROTOCOL / "reference/total_eval.py"
        evaluator.write_bytes(evaluator.read_bytes() + b"\nraise RuntimeError('must not execute')\n")
        with self.assertRaisesRegex(RoutingError, "pin-mismatch"):
            self.capture()
        evaluator.write_bytes(self.files[runtime.PROTOCOL + "/reference/total_eval.py"])
        (evaluator.parent / "plugin.py").write_text("raise RuntimeError('must not execute')")
        with self.assertRaisesRegex(RoutingError, "closure-mismatch"):
            self.capture()

    def test_modified_retained_image_cannot_be_consumed_or_substitute_a_validator(self):
        altered = dict(self.files)
        altered[runtime.PROTOCOL + "/reference/total_eval.py"] = b"raise RuntimeError('not executed')"
        with self.assertRaisesRegex(RoutingError, "pin-mismatch"):
            runtime.Runtime(self.protocol, self.parent, altered)
        self.prepare()
        image_path = self.workspace / ".workspace1/runtime-image.json"
        image_path.write_bytes(image_path.read_bytes() + b" ")
        with self.assertRaisesRegex(RoutingError, "image-substitution"):
            self.capture()

    def test_captured_validator_bytes_are_consumed_despite_later_path_substitution(self):
        checkout = self.mirror()
        schema = checkout / runtime.PROTOCOL / "schemas/common.schema.json"
        schema.write_bytes(b'{"untrusted":"must not be consumed"}')
        image = runtime.Runtime(checkout, self.parent, self.files)
        try:
            expected = json.loads(self.files[runtime.PROTOCOL + "/schemas/common.schema.json"])
            self.assertEqual(image.core.schemas.documents["common.schema.json"], expected)
            raw = self.files[runtime.PROTOCOL + "/reference/total_eval.py"]
            evaluator = image.kernel.EvaluatorImage(raw, runtime.sha(raw))
            self.assertEqual(evaluator.evaluate("identity-octets", b"safe"), b"safe")
            self.assertNotIn("__import__", evaluator._evaluate.__globals__["__builtins__"])
            self.assertNotIn("open", evaluator._evaluate.__globals__["__builtins__"])
        finally:
            image.close()
        malformed = dict(self.files)
        index = json.loads(malformed["protocols/index.json"])
        current = next(p for p in index["profiles"] if p["name"] == runtime.PROFILE)
        current["conformance"] = "untrusted.py"
        malformed["protocols/index.json"] = runtime.encode(index)
        with self.assertRaisesRegex(RoutingError, "exact-index-profile"):
            runtime.Runtime(self.protocol, self.parent, malformed)

    def test_malformed_external_scope_and_rights_are_closed_refusals_not_programs(self):
        self.prepare()
        with self.assertRaisesRegex(RoutingError, "closed"):
            g.initialize(self.workspace, [{"subject": "not-an-object", "form": "supplied-octets", "path": None}],
                         rights=self.rights, expires_utc=EXPIRY, now=NOW)
        policy = json.loads((self.workspace / ".workspace1/policy.json").read_bytes())
        policy["rights"] = [{"execute": True}]
        with self.assertRaisesRegex(RoutingError, "policy-rights"):
            g.validate_policy(policy)

    def test_denied_or_expired_capture_does_not_reach_source_path_or_decoder(self):
        self.prepare(form="file-octets", path=self.source, rights={"retention"})
        with mock.patch.object(g, "fixture_path", side_effect=AssertionError("source access")):
            with self.assertRaisesRegex(ValueError, "capability-denied:capture"):
                g.capture(self.workspace, "input", SUBJECT, form="file-octets", path=self.source,
                          synthetic_fixture=True, now=NOW, **CAPTURE)
        with mock.patch.object(g, "fixture_path", side_effect=AssertionError("source access")):
            with self.assertRaisesRegex(RoutingError, "expired"):
                g.capture(self.workspace, "input", SUBJECT, form="file-octets", path=self.source,
                          synthetic_fixture=True, now=EXPIRY, **CAPTURE)

    def test_cli_octet_decoding_waits_for_current_capture_and_retention_rights(self):
        self.prepare(rights={"retention"})
        with mock.patch.object(g, "decode_supplied", side_effect=AssertionError("source decoded")):
            with self.assertRaisesRegex(ValueError, "capability-denied:capture"):
                g.capture(self.workspace, "input", SUBJECT, form="supplied-octets",
                          octets_base64="bm90IGF1dGhvcml6ZWQ=", now=NOW, **CAPTURE)

    def test_source_file_is_no_follow_bounded_stable_not_coherent_and_not_adoptable(self):
        self.prepare(form="file-octets", path=self.source)
        before = snapshot(self.fixtures)
        with metadata_guard([self.fixtures], [self.source]) as reads:
            result = g.capture(self.workspace, "input", SUBJECT, form="file-octets", path=self.source,
                               synthetic_fixture=True, now=NOW, **CAPTURE)
        self.assertEqual(reads, [str(self.source)])
        self.assertEqual(before, snapshot(self.fixtures))
        self.assertEqual(result["guarantees"]["observation"]["method"], "stable-descriptor-not-coherent")
        g.run_lenses(self.workspace, "input", strategy="adaptive", now=NOW, **RUN)
        with g.host(self.workspace, now=NOW) as value:
            job = value.state["jobs"]["input"]
            for ref in job["observations"] + [a["result"] for a in job["attempts"]]:
                self.assertFalse(value.c.body(ref)["restrictions"]["rights"]["adoption"])
        prepared = g.stage(self.workspace, "input", "accept-input", now=NOW, **STAGE)
        with self.assertRaisesRegex(RoutingError, "native-snapshot-adoption-disabled"):
            g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)

    def test_links_hardlinks_credentials_and_control_overlap_are_refused_before_contents(self):
        self.prepare(form="file-octets", path=self.source)
        original = self.fixtures / "opaque.data"
        self.source.rename(original)
        self.source.symlink_to(original)
        with metadata_guard([self.fixtures], []), self.assertRaises((ValueError, OSError, RoutingError)):
            g.capture(self.workspace, "input", SUBJECT, form="file-octets", path=self.source,
                      synthetic_fixture=True, now=NOW, **CAPTURE)
        self.source.unlink()
        os.link(original, self.source)
        with self.assertRaisesRegex((ValueError, RoutingError), "hardlink"):
            g.capture(self.workspace, "input", SUBJECT, form="file-octets", path=self.source,
                      synthetic_fixture=True, now=NOW, **CAPTURE)
        with g.host(self.workspace, now=NOW) as value:
            for path in (self.fixtures / ".env", self.fixtures / ".ssh/id_rsa", self.workspace / "registry.json"):
                with self.subTest(path=path), self.assertRaises(RoutingError):
                    g.fixture_path(value, path, "file-octets")
        self.assertFalse(self.read_state()["jobs"])

    def test_directory_fixture_reads_only_one_level_metadata_and_never_claims_a_snapshot(self):
        (self.fixtures / "nested").mkdir()
        (self.fixtures / "nested/secret.fixture").write_bytes(b"NEVER READ")
        self.prepare(form="directory-metadata-fixture", path=self.fixtures)
        before = snapshot(self.fixtures)
        with metadata_guard([self.fixtures], []):
            result = g.capture(self.workspace, "input", SUBJECT, form="directory-metadata-fixture",
                               path=self.fixtures, synthetic_fixture=True, now=NOW, **CAPTURE)
        with g.host(self.workspace, now=NOW) as value:
            captured = value.c.body(result["observations"][0])
            raw = base64.b64decode(captured["octets_b64"])
            fixture = json.loads(raw)
            self.assertEqual(fixture["consistency"], "one-level-metadata-not-coherent")
            self.assertEqual(len(fixture["entries"]), 2)
            self.assertNotIn(b"NEVER READ", raw)
            self.assertNotIn(b"secret.fixture", raw)
            self.assertFalse(captured["restrictions"]["rights"]["adoption"])
        self.assertEqual(before, snapshot(self.fixtures))
        with self.assertRaisesRegex(RoutingError, "entry-bound"):
            g.capture(self.workspace, "too-many", SUBJECT, form="directory-metadata-fixture",
                      path=self.fixtures, max_entries=1, synthetic_fixture=True, now=NOW, **CAPTURE)

    def test_opaque_domains_remain_refused_under_strict_mapping_without_losing_observation(self):
        self.prepare(max_attempts=32)
        for index, raw in enumerate((b"\xff\xfe", b'{"a":1,"a":2}', b'{"a":9007199254740993}', b'{"a":NaN}')):
            with self.subTest(raw=raw):
                job = "case-" + str(index)
                self.capture(raw, job)
                result = g.run_lenses(self.workspace, job, strategy="strict-field", field="a", now=NOW, **RUN)
                self.assertEqual(result["outcome"], "refused")
                self.assertEqual(result["guarantees"]["observation"]["status"], "verified")
                self.assertEqual(result["guarantees"]["semantic_fidelity"]["status"], "refused")
        for raw in (b"x" * 65537, iter([b"x"])):
            with self.assertRaisesRegex(ValueError, "finite-bounded"):
                self.capture(raw, "invalid")
        cycle = []
        cycle.append(cycle)
        with self.assertRaisesRegex(ValueError, "cyclic"):
            self.image.core.octets(cycle)

    def test_adoption_shaped_data_cannot_self_adopt_and_replay_is_not_fidelity(self):
        self.prepare()
        result = self.candidate(b'{"adopt":true,"rights":["execution"],"safe_deployment":"verified"}')
        self.assertEqual(result["guarantees"]["semantic_fidelity"]["status"], "unproven")
        self.assertEqual(result["guarantees"]["safe_deployment"]["status"], "refused")
        with g.host(self.workspace, now=NOW) as value:
            self.assertEqual(value.c.projection()["entries"], [])
            receipt = result["guarantees"]["rapp_integrity"]
            with self.assertRaisesRegex(ValueError, "wrong-validator-or-guarantee"):
                value.c.verify_receipt(receipt["receipt"], "semantic_fidelity", receipt["subject"])
        with self.assertRaisesRegex(RoutingError, "explicit"):
            g.stage(self.workspace, "input", "accept-input", now=NOW, allow_local_synthesis=True, allow_retention=True)
        self.assertIsNone(self.status()["adopted_projection_head"])

    def test_partial_mapping_cannot_stage_as_complete_fidelity(self):
        self.prepare()
        self.capture(b'{"workspace":{"label":"partial"},"uncovered":true}')
        result = g.run_lenses(self.workspace, "input", strategy="strict-field", now=NOW, **RUN)
        self.assertEqual(result["outcome"], "candidate")
        with self.assertRaisesRegex(ValueError, "correspondence"):
            g.stage(self.workspace, "input", "accept-input", now=NOW, **STAGE)
        self.assertFalse(self.read_state()["stages"])

    def test_refusal_exhaust_is_an_actual_necessary_synthesis_input_to_fallback(self):
        self.prepare()
        result = self.candidate(b"[1,[2,3]]", strategy="adaptive")
        self.assertEqual([a["kind"] for a in result["attempts"]], ["refused", "stopped", "candidate"])
        with g.host(self.workspace, now=NOW) as value:
            context = value.c.body(result["feedback"]["source"])
            raw = base64.b64decode(context["octets_b64"])
            parsed = json.loads(raw)
            self.assertEqual(parsed["exhaust"], value.c.body(result["feedback"]["exhaust"]))
            self.assertEqual(parsed["refusal"], value.c.body(result["feedback"]["refusal"]))
            derived = value.c.body(result["attempts"][-1]["result"])
            self.assertEqual(derived["actual_reads"], derived["necessary_reads"])
            self.assertEqual(derived["actual_reads"], derived["synthesis_reads"])
            self.assertEqual(derived["actual_reads"][0]["expected"], runtime.sha(raw))
            self.assertEqual(derived["environment"], [])
            self.assertFalse(parsed["grants_authority"])
        before = self.read_state()
        g.run_lenses(self.workspace, "input", strategy="adaptive", now=NOW, **RUN)
        self.assertEqual(before, self.read_state())

    def test_feedback_budget_refusal_preserves_attempts_refusal_and_exhaust(self):
        self.prepare(max_total_octets=100)
        result = self.candidate(b"\x00" * 100, strategy="adaptive")
        self.assertEqual(result["outcome"], "stopped")
        self.assertEqual(result["reason"], "feedback-budget-or-rights-refused")
        self.assertEqual([a["kind"] for a in result["attempts"]], ["refused", "stopped", "stopped"])
        self.assertEqual(self.status()["root_budget"]["octets_used"], 100)
        with g.host(self.workspace, now=NOW) as value:
            for attempt in result["attempts"]:
                value.c.frame(attempt["result"])

    def test_root_stop_reserve_and_attempt_budget_survive_restart_and_cannot_reset(self):
        self.prepare(max_attempts=1)
        result = self.candidate(b"not json", strategy="strict-field")
        status = self.status()
        self.assertIsNotNone(status["root_budget"]["terminal_stop"])
        self.assertEqual(status["root_budget"]["attempts_used"], 1)
        self.assertEqual(len(result["attempts"]), 2)
        with self.assertRaisesRegex(RoutingError, "durable-root-stop"):
            self.capture(b"new named child", "renamed-child")
        before = self.read_state()
        g.run_lenses(self.workspace, "input", strategy="strict-field", now=NOW, **RUN)
        self.assertEqual(before, self.read_state())
        with self.assertRaisesRegex(RoutingError, "reviewed-transition"):
            g.initialize(self.workspace, self.scopes, rights=self.rights, expires_utc=EXPIRY, max_attempts=2, now=NOW)

    def test_reserved_stop_is_retained_when_there_is_no_room_for_a_lens(self):
        self.prepare(max_frames=9)
        result = self.candidate()
        self.assertEqual(result["outcome"], "stopped")
        self.assertEqual(result["reason"], "root-frame-budget")
        self.assertIsNone(result["attempts"][0]["lens"])
        with g.host(self.workspace, now=NOW) as value:
            self.assertTrue(value.c.body(result["attempts"][0]["result"])["reserved_stop"])
            self.assertLessEqual(value.c.verify_history()["frames"], 9)

    def test_stage_has_no_effect_and_complete_manager_frontier_race_rolls_back(self):
        self.prepare()
        prepared = self.ready()
        self.assertIsNone(self.status()["adopted_projection_head"])
        before = self.read_state()["checkpoint"]
        self.registry["forgotten"] = [wm.legacy_local_id("/fictional/suppressed")]
        self.save_registry()
        with self.assertRaisesRegex(RoutingError, "complete-frontier-CAS"):
            g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        self.assertEqual(before, self.read_state()["checkpoint"])

    def test_order_organization_world_and_policy_are_not_missing_from_frontier(self):
        self.prepare()
        prepared = self.ready()
        changes = [
            ("generated_utc", "2026-09-15T04:31:00.000Z"),
            ("scan_roots", ["/fictional/new-scope"]),
            ("organization", {**wm.default_organization(),
                              "groups": [{"id": "root", "name": "Different", "parent": None}]}),
        ]
        original = copy.deepcopy(self.registry)
        for key, changed in changes:
            with self.subTest(field=key):
                self.registry = {**original, key: changed}
                self.save_registry()
                with self.assertRaisesRegex(RoutingError, "complete-frontier-CAS"):
                    g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        self.registry = original
        self.save_registry()
        policy_file = self.workspace / ".workspace1/policy.json"
        policy = json.loads(policy_file.read_bytes())
        policy["rights"].remove("adoption")
        g.write_json(policy_file, policy)
        with self.assertRaisesRegex(ValueError, "policy/configuration-substitution"):
            g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)

    def test_source_reobservation_and_suppression_frontiers_refuse_staged_work(self):
        self.prepare()
        prepared = self.ready()
        self.capture(b"new content same native subject", "reobserved")
        with self.assertRaisesRegex(ValueError, "complete-frontier-CAS"):
            g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        with g.host(self.workspace, now=NOW) as value:
            with value.transaction():
                value.c.suppress(SUBJECT)
        self.candidate(b"third rendition", "third")
        third = g.stage(self.workspace, "third", "third-adoption", now=NOW, **STAGE)
        with self.assertRaisesRegex(ValueError, "suppression"):
            g.adopt(self.workspace, "third-adoption", third["token"], now=NOW, **ADOPT)

    def test_adoption_is_one_commit_with_crash_recovery_lost_ack_and_idempotence(self):
        self.prepare()
        prepared = self.ready()
        before = self.read_state()
        def crash(stage):
            if stage == "before-commit":
                raise RuntimeError("synthetic interruption")
        with self.assertRaises(RuntimeError):
            g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, fault=crash, **ADOPT)
        self.assertEqual(before, self.read_state())
        def lost_ack(stage):
            if stage == "after-commit":
                raise RuntimeError("synthetic lost ack")
        with self.assertRaises(RuntimeError):
            g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, fault=lost_ack, **ADOPT)
        first = g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        second = g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        self.assertEqual(first, second)
        self.assertTrue(first["idempotent"])
        g.recover(self.workspace, allow_retention=True, now=NOW)
        self.assertEqual(json.loads((self.workspace / ".workspace1/state.json").read_bytes()), self.read_state())

    def test_process_death_before_commit_does_not_leave_partial_manager_or_protocol_adoption(self):
        self.prepare()
        prepared = self.ready()
        before = self.read_state()
        script = """
import os, sys
sys.path.insert(0, sys.argv[1])
import workspace1_manager as g
g.adopt(sys.argv[2], 'accept-input', sys.argv[3], allow_adoption=True, allow_retention=True,
        now=sys.argv[4], fault=lambda phase: os._exit(93) if phase == 'before-commit' else None)
"""
        completed = subprocess.run([sys.executable, "-B", "-c", script, str(Path(g.__file__).parent),
                                    str(self.workspace), prepared["token"], NOW], capture_output=True, timeout=60)
        self.assertEqual(completed.returncode, 93, completed.stderr.decode())
        self.assertEqual(before, self.read_state())
        g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        self.assertEqual(self.read_state()["stages"]["accept-input"]["status"], "adopted")

    def test_wrong_controller_token_and_operation_content_are_not_idempotent_retries(self):
        self.prepare()
        prepared = self.ready()
        with self.assertRaisesRegex(RoutingError, "token-required"):
            g.adopt(self.workspace, "accept-input", "0" * 64, now=NOW, **ADOPT)
        self.candidate(b"other", "other")
        with self.assertRaisesRegex(RoutingError, "idempotency-conflict"):
            g.stage(self.workspace, "other", "accept-input", now=NOW, **STAGE)
        self.assertEqual(prepared["request"], self.read_state()["stages"]["accept-input"]["request"])

    def test_local_single_writer_and_verified_owned_fork_latch_persist(self):
        self.prepare()
        with g.host(self.workspace, now=NOW) as value:
            with self.assertRaises(RoutingError):
                self.status()
            original = value.c._head()
            payload = dict(original["payload"], world_id="rival-local-data")
            fork = value.image.core.r.build_frame("body.pulse", self.identity["rappid"], 0, NOW, payload, None)
            with self.assertRaisesRegex(ValueError, "fork-latched"):
                value.c.observe_owned_fork(value.image.core.octets(fork))
        with self.assertRaisesRegex(ValueError, "fork-latched"):
            self.capture()

    def test_current_time_is_monotonic_and_historical_receipts_do_not_renew_rights(self):
        self.prepare()
        result = self.candidate()
        receipt = result["guarantees"]["current_authorization"]
        with g.host(self.workspace, now=NOW) as value:
            with self.assertRaisesRegex(ValueError, "external-controller-query"):
                value.c.verify_receipt(receipt["receipt"], "current_authorization", receipt["subject"], current=True)
        with self.assertRaisesRegex(ValueError, "clock-rollback"):
            g.inspect(self.workspace, now="2026-09-15T04:29:00.000Z")
        with self.assertRaisesRegex(RoutingError, "not-currently-authorized"):
            g.history(self.workspace, allow_retention=True, now=EXPIRY)

    def legacy_pointer(self, path, name, world=None):
        return {"name": name, "path": str(path), "kind": "directory", "rappid": None,
                "mode": None, "world_id": world, "tags": [], "pointer_version": 1,
                "pointer_type": "local-directory", "pointer_id": wm.legacy_local_id(path), "selection": "exact"}

    def test_v1_migration_is_registry_only_preserves_frontier_and_refuses_silent_binding(self):
        a, b = self.fixtures / "first", self.fixtures / "second"
        a.mkdir()
        b.mkdir()
        self.registry["workspaces"] = [self.legacy_pointer(b, "second", "world-B"),
                                       self.legacy_pointer(a, "first", "world-A")]
        self.registry["forgotten"] = [wm.legacy_local_id("/fictional/forgotten")]
        self.save_registry()
        self.prepare()
        old_registry = (self.workspace / "registry.json").read_bytes()
        before = snapshot(self.fixtures)
        with metadata_guard([self.fixtures], []):
            captured = g.migrate_metadata(self.workspace, "migration", metadata_only=True, now=NOW, **CAPTURE)
            g.run_lenses(self.workspace, "migration", strategy="identity", now=NOW, **RUN)
            prepared = g.stage(self.workspace, "migration", "metadata-adoption", now=NOW, **STAGE)
            with self.assertRaisesRegex(RoutingError, "explicit-safe-readd"):
                g.adopt(self.workspace, "metadata-adoption", prepared["token"], now=NOW, **ADOPT)
        self.assertEqual(captured["migration"]["unresolved"],
                         [p["pointer_id"] for p in self.registry["workspaces"]])
        self.assertEqual(captured["migration"]["worlds"], [self.registry["world_id"], "world-B", "world-A"])
        self.assertEqual(old_registry, (self.workspace / "registry.json").read_bytes())
        self.assertEqual(before, snapshot(self.fixtures))
        self.assertTrue(all(p["pointer_version"] == 1 for p in wm.load_registry(self.workspace)["workspaces"]))

    def test_explicit_safe_readd_needs_a_new_metadata_observation_old_v1_stays_unresolved(self):
        selected = self.fixtures / "selected"
        selected.mkdir()
        self.registry["workspaces"] = [self.legacy_pointer(selected, "selected")]
        self.save_registry()
        self.prepare()
        g.migrate_metadata(self.workspace, "legacy", metadata_only=True, now=NOW, **CAPTURE)
        with contextlib.redirect_stdout(io.StringIO()):
            wm.local_action(argparse.Namespace(workspace=str(self.workspace), path=str(selected),
                                                command="re-add", rapp1_path=str(self.parent)))
        modern = wm.load_registry(self.workspace)["workspaces"][0]
        self.assertEqual(modern["pointer_version"], 2)
        self.assertEqual(modern["filesystemIdentity"], directory_identity(selected))
        fresh = g.migrate_metadata(self.workspace, "readded", metadata_only=True, now=NOW, **CAPTURE)
        self.assertFalse(fresh["migration"]["unresolved"])
        self.assertTrue(self.read_state()["jobs"]["legacy"]["migration"]["unresolved"])
        g.run_lenses(self.workspace, "readded", strategy="identity", now=NOW, **RUN)
        prepared = g.stage(self.workspace, "readded", "metadata-only", now=NOW, **STAGE)
        g.adopt(self.workspace, "metadata-only", prepared["token"], now=NOW, **ADOPT)
        before = (self.workspace / "registry.json").read_bytes()
        with metadata_guard([self.fixtures], []):
            g.materialize(self.workspace, now=NOW, **PROJECT)
        self.assertEqual(before, (self.workspace / "registry.json").read_bytes())
        editor = json.loads((self.workspace / ".workspace1/estate.code-workspace").read_bytes())
        self.assertEqual(editor["folders"], [{"name": "RAPP Workspace/1 manager", "path": ".."}])

    def test_migration_stale_capture_frontier_cannot_be_repaired_by_a_fresh_stage(self):
        self.prepare()
        g.migrate_metadata(self.workspace, "migration", metadata_only=True, now=NOW, **CAPTURE)
        self.registry["generated_utc"] = "2026-09-15T04:32:00.000Z"
        self.save_registry()
        g.run_lenses(self.workspace, "migration", strategy="identity", now=NOW, **RUN)
        prepared = g.stage(self.workspace, "migration", "metadata-only", now=NOW, **STAGE)
        with self.assertRaisesRegex(RoutingError, "migration-registry-frontier-stale"):
            g.adopt(self.workspace, "metadata-only", prepared["token"], now=NOW, **ADOPT)

    def test_inert_json_markdown_editor_are_deterministic_and_never_instructions_or_routes(self):
        self.prepare()
        raw = b'<img src="https://example.invalid/x"><script>run()</script>\x1b[2J\n![x](url)'
        prepared = self.ready(raw=raw)
        g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        first = g.materialize(self.workspace, now=NOW, **PROJECT)
        files = {name: (self.workspace / ".workspace1" / name).read_bytes()
                 for name in ("view.json", "view.md", "estate.code-workspace")}
        second = g.materialize(self.workspace, now=NOW, **PROJECT)
        self.assertEqual(first, second)
        self.assertEqual(files, {name: (self.workspace / ".workspace1" / name).read_bytes() for name in files})
        for content in files.values():
            for dangerous in (b"<img", b"<script>", b"\x1b", b"https://", b"!["):
                self.assertNotIn(dangerous, content)
        for name in ("SKILL.md", "CLAUDE.md", "AGENTS.md", "tasks.json", "settings.json"):
            self.assertFalse((self.workspace / ".workspace1" / name).exists())
        self.assertFalse(json.loads(files["view.json"])["authority"])
        self.assertEqual(len(json.loads(files["estate.code-workspace"])["folders"]), 1)
        for name in files:
            self.assertEqual((self.workspace / ".workspace1" / name).stat().st_mode & 0o111, 0)

    def test_projection_crash_recovery_and_suppression_staleness_never_make_views_authority(self):
        self.prepare()
        prepared = self.ready()
        g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        def crash(phase):
            if phase == "after-view.json":
                raise RuntimeError("synthetic projection interruption")
        with self.assertRaises(RuntimeError):
            g.materialize(self.workspace, now=NOW, fault=crash, **PROJECT)
        self.assertTrue(self.status()["projections"]["recovery_required"])
        g.recover(self.workspace, now=NOW, **PROJECT)
        self.assertFalse(self.status()["projections"]["recovery_required"])
        self.registry["forgotten"] = [wm.legacy_local_id("/fictional/new-suppression")]
        self.save_registry()
        self.assertFalse(self.status()["projections"]["manager_frontier_current"])
        with self.assertRaisesRegex(RoutingError, "projection-frontier-stale"):
            g.materialize(self.workspace, now=NOW, **PROJECT)

    def test_focus_exposes_refused_assurances_without_adopting_or_routing_the_job(self):
        self.prepare()
        self.candidate(b"not a supported mapping", strategy="strict-field")
        g.materialize(self.workspace, job_id="input", now=NOW, **PROJECT)
        document = json.loads((self.workspace / ".workspace1/view.json").read_bytes())
        self.assertEqual(document["projection"]["entries"], [])
        self.assertFalse(document["authority"])
        self.assertEqual(document["assurances"][0]["guarantees"]["semantic_fidelity"]["status"], "refused")
        self.assertEqual(set(document["assurances"][0]["guarantees"]), set(runtime.GUARANTEES))

    def test_fresh_explicit_focus_can_exclude_stale_historical_adoptions_without_resetting_seed(self):
        self.prepare()
        prepared = self.ready()
        g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        seed = self.read_state()["seed_lineage"]
        self.registry["generated_utc"] = "2026-09-15T04:33:00.000Z"
        self.save_registry()
        self.candidate(b"new frontier new captured view", "fresh")
        fresh = g.stage(self.workspace, "fresh", "accept-fresh", now=NOW, **STAGE)
        g.adopt(self.workspace, "accept-fresh", fresh["token"], now=NOW, **ADOPT)
        with self.assertRaisesRegex(RoutingError, "projection-frontier-stale"):
            g.materialize(self.workspace, now=NOW, **PROJECT)
        g.materialize(self.workspace, job_id="fresh", now=NOW, **PROJECT)
        document = json.loads((self.workspace / ".workspace1/view.json").read_bytes())
        self.assertEqual([p["operation"] for p in document["projection"]["entries"]], ["accept-fresh"])
        self.assertTrue(self.status()["projections"]["manager_frontier_current"])
        self.assertEqual(seed, self.read_state()["seed_lineage"])

    def test_materialization_refuses_output_links_and_capture_does_not_grant_it(self):
        self.prepare(rights={"capture", "retention"})
        result = self.capture()
        self.assertEqual(result["guarantees"]["semantic_fidelity"]["status"], "unproven")
        self.assertEqual(result["guarantees"]["current_authorization"]["status"], "refused")
        with self.assertRaisesRegex(ValueError, "capability-denied:materialization"):
            g.materialize(self.workspace, now=NOW, **PROJECT)
        self.assertFalse((self.workspace / ".workspace1/view.json").exists())

    def test_manager_owned_outputs_refuse_symlink_escape(self):
        self.prepare()
        prepared = self.ready()
        g.adopt(self.workspace, "accept-input", prepared["token"], now=NOW, **ADOPT)
        (self.workspace / ".workspace1/view.json").symlink_to(self.source)
        original = self.source.read_bytes()
        with self.assertRaisesRegex(RoutingError, "symlink"):
            g.materialize(self.workspace, now=NOW, **PROJECT)
        self.assertEqual(self.source.read_bytes(), original)

    def test_historical_parent_integrity_works_when_fresh_evaluator_is_unavailable(self):
        checkout = self.mirror()
        self.prepare(checkout=checkout)
        self.candidate()
        (checkout / runtime.PROTOCOL / "reference/total_eval.py").unlink()
        result = g.history(self.workspace, allow_retention=True, now=NOW)
        self.assertEqual(result["rapp_integrity"], "verified")
        self.assertGreater(result["frames"], 0)
        self.assertEqual(result["semantic_fidelity"], "historical-evaluator-unavailable")
        self.assertEqual(result["current_authorization"], "not-inferred")
        with self.assertRaises((OSError, RoutingError)):
            self.status()

    def test_coverage_context_delta_portability_and_disabled_learning_remain_distinct_gates(self):
        self.prepare()
        with g.host(self.workspace, now=NOW) as value:
            kernel, c = value.image.kernel, value.c
            empty = kernel.merge_measurement({"a": 1}, {"b": 1}, {"pairs": [["a", "a"]]})
            self.assertEqual(empty["status"], "unmeasured")
            self.assertIsNone(empty["numerator"])
            mismatch = kernel.merge_measurement({"a": 1}, {"b": 2}, {"pairs": [["a", "b"]]})
            self.assertTrue(mismatch["conflicts"])
            self.assertEqual(len(mismatch["retained"]), 2)
            self.assertEqual(kernel.reattach_measurement({"a": "necessary"}, {})["status"], "unresolved")
            self.assertEqual(kernel.delta_plan(["a"], ["a"], NOW, NOW, [], [])["mode"], "baseline-required")
            with self.assertRaisesRegex(ValueError, "generated-output"):
                kernel.delta_plan(["out"], ["out"], EXPIRY, NOW, [], ["out"])
            for operation in ("live_migration", "native_rebinding", "partitioned_effect", "learned_semantic_capability",
                              "redistribution", "execution", "network", "loopback", "imports", "live_delta"):
                with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "disabled"):
                    c.require_effect(SUBJECT, operation)
            with self.assertRaisesRegex(ValueError, "output-scope"):
                c.export_frames(self.fixtures / "not-manager-owned")

    def test_actual_negative_enumeration_and_environment_read_obligations_are_not_elided(self):
        self.prepare()
        self.capture(b'{"a":1}')
        with g.host(self.workspace, now=NOW) as value:
            c = value.c
            source = value.state["jobs"]["input"]["source"]
            lens = c.synthesize(SUBJECT, source, "json-field", "missing")
            result = c.execute(SUBJECT, lens)
            self.assertEqual(result["negative_reads"][0]["kind"], "negative")
            with self.assertRaisesRegex(ValueError, "ambient-environment"):
                c.execute(SUBJECT, lens, environment=["HOME"])
            good = c.synthesize(SUBJECT, source, "json-field", "a")
            with self.assertRaisesRegex(ValueError, "actual-read-trace-forgery"):
                c.execute(SUBJECT, good, actual_override=[])
            result = c.execute(SUBJECT, good)
            self.assertEqual(c.body(result["frame"])["enumerations"][0]["kind"], "enumeration")

    def test_public_demo_has_radically_different_shapes_fallback_stable_refusal_and_no_real_paths(self):
        output = (self.root / "demo").relative_to(Path.cwd())
        report = g.demo(self.protocol, self.parent, output)
        self.assertGreater(report["rapp_frames_verified"], 0)
        self.assertEqual([p["outcome"] for p in report["results"]], ["adopted", "adopted", "refused"])
        for result in report["results"]:
            self.assertEqual(set(result["guarantees"]), set(runtime.GUARANTEES))
            self.assertEqual(result["guarantees"]["safe_deployment"]["status"], "refused")
        for result in report["results"][:2]:
            self.assertEqual([a["kind"] for a in result["attempts"]], ["refused", "stopped", "candidate"])
            self.assertIsNotNone(result["feedback"])
        encoded = json.dumps(report)
        for value in (str(self.root), str(Path.home()), str(self.protocol), str(self.parent)):
            self.assertNotIn(value, encoded)
        self.assertFalse(report["signed_activation"])


if __name__ == "__main__":
    unittest.main()
