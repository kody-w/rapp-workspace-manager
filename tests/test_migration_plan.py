import contextlib
import copy
import io
import itertools
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import native_ai as native
import routing_io as fs
import workspace_manager as manager
from support import fixture_directory, snapshot
from test_federation import FakeRapp
from test_native_ai import session_id


class MigrationPlanningTests(unittest.TestCase):
    A = "/synthetic/profiles/A"
    B = "/synthetic/profiles/B"
    a = "/synthetic/profiles/a"
    C = "/synthetic/profiles/C"
    D = "/synthetic/profiles/D"
    original_identity = [17, 101]
    replacement_identity = [17, 202]

    def pointer(self, path, identity, number=1):
        return native.pointer(
            "copilot", path, "copilot-session", session_id(number),
            profile_identity=identity, nativeSessionId=session_id(number),
            metadata={}, sourceStamp=None, availability="missing-metadata",
        )

    def result(self, catalog):
        return {
            "provider": "copilot", "catalog": list(catalog), "observations": [],
            "profileRoots": list(dict.fromkeys(item["profileRoot"] for item in catalog)),
            "profileIdentities": {item["profileRoot"]: item["profileIdentity"] for item in catalog},
        }

    def test_case_alias_ambiguity_refuses_every_candidate_and_profile_order(self):
        legacy = native.legacy_pointer_id("copilot", self.A, "copilot-session", session_id())
        state = manager.empty_provider()
        state.update(
            profileRoots=[self.A], profileIdentities={self.A: self.original_identity},
            forgotten=[legacy],
        )
        original = self.pointer(self.B, self.original_identity)
        replacement = self.pointer(self.a, self.replacement_identity)
        locations = {
            self.A: self.replacement_identity,
            self.a: self.replacement_identity,
            self.B: self.original_identity,
        }
        for order in itertools.permutations((original, replacement)):
            for roots in itertools.permutations((self.B, self.a)):
                result = self.result(order)
                result["profileRoots"] = list(roots)
                before_state, before_result = copy.deepcopy(state), copy.deepcopy(result)
                with self.subTest(order=[item["profileRoot"] for item in order], roots=roots):
                    with mock.patch.object(manager, "same_location", side_effect=lambda left, right: locations[str(left)] == locations[str(right)]):
                        with self.assertRaisesRegex(fs.RoutingError, "native-identity-ambiguous"):
                            manager.remap_native_identities(state, result)
                    self.assertEqual(state, before_state)
                    self.assertEqual(result, before_result)
                    self.assertEqual(state["forgotten"], [legacy])

    def test_complete_candidate_claims_cannot_split_one_original_identity(self):
        legacy = native.legacy_pointer_id("copilot", self.A, "copilot-session", session_id())
        candidates = (
            self.pointer(self.B, self.original_identity),
            self.pointer(self.C, self.replacement_identity),
        )
        for tracked in ("selected", "forgotten"):
            for order in itertools.permutations(candidates):
                state = manager.empty_provider()
                state.update(profileRoots=[self.A], **{tracked: [legacy]})
                before = copy.deepcopy(state)
                # A legacy locator appears to resolve to two candidates during
                # planning. Per-candidate checks alone cannot establish a target.
                def moving_locator(left, right):
                    return str(left) == self.A or str(left) == str(right)
                with self.subTest(tracked=tracked, order=[item["profileRoot"] for item in order]):
                    with mock.patch.object(manager, "same_location", side_effect=moving_locator):
                        with self.assertRaisesRegex(fs.RoutingError, "native-identity-ambiguous"):
                            manager.remap_native_identities(state, self.result(order))
                    self.assertEqual(state, before)

    def test_valid_migration_is_order_independent_and_retains_unmatched_ids(self):
        suppressed = native.legacy_pointer_id("copilot", self.A, "copilot-session", session_id())
        selected = native.legacy_pointer_id("copilot", self.C, "copilot-session", session_id())
        unmatched_suppression, unmatched_selection = "copilot:" + "e" * 64, "copilot:" + "f" * 64
        state = manager.empty_provider()
        state.update(
            profileRoots=[self.A, self.C],
            profileIdentities={self.A: self.original_identity, self.C: [17, 303]},
            forgotten=[suppressed, unmatched_suppression],
            selected=[selected, unmatched_selection],
        )
        moved = self.pointer(self.B, self.original_identity)
        chosen = self.pointer(self.C, [17, 303])
        unselected = self.pointer(self.D, [17, 404])
        location_ids = {
            self.A: self.original_identity, self.B: self.original_identity,
            self.C: [17, 303], self.D: [17, 404],
        }
        expected = None
        for order in itertools.permutations((moved, chosen, unselected)):
            for roots in itertools.permutations((self.B, self.C, self.D)):
                result = self.result(order)
                result["profileRoots"] = list(roots)
                before = copy.deepcopy(state)
                with mock.patch.object(manager, "same_location", side_effect=lambda left, right: location_ids[str(left)] == location_ids[str(right)]):
                    actual = manager.remap_native_identities(state, result)
                self.assertEqual(actual[0], sorted([chosen["pointer_id"], unmatched_selection]))
                self.assertEqual(actual[1], {moved["pointer_id"], unmatched_suppression})
                if expected is None:
                    expected = actual
                self.assertEqual(actual, expected)
                self.assertEqual(state, before)

    def test_suppression_wins_over_selected_alias_in_the_validated_plan(self):
        selected = native.legacy_pointer_id("copilot", self.A, "copilot-session", session_id())
        suppressed = native.legacy_pointer_id("copilot", self.B, "copilot-session", session_id())
        state = manager.empty_provider()
        state.update(
            profileRoots=[self.A, self.B],
            profileIdentities={self.A: self.original_identity, self.B: self.original_identity},
            selected=[selected], forgotten=[suppressed],
        )
        candidate = self.pointer(self.C, self.original_identity)
        with mock.patch.object(manager, "same_location", return_value=True):
            selected_after, forgotten_after, _ = manager.remap_native_identities(state, self.result([candidate]))
        self.assertEqual(selected_after, [])
        self.assertEqual(forgotten_after, {candidate["pointer_id"]})
        self.assertEqual(state["selected"], [selected])
        self.assertEqual(state["forgotten"], [suppressed])

    def test_observation_order_uses_the_same_immutable_suppression_plan(self):
        paths = [path + "/Grokbot.app" for path in (self.A, self.B, self.a)]
        old, moved, replacement = paths
        legacy = native.legacy_pointer_id("grokbot", old, "app-observation", None)
        state = manager.empty_provider()
        state.update(
            profileRoots=[old], profileIdentities={old: self.original_identity},
            forgotten=[legacy],
        )
        observations = [{
            "provider": "grokbot", "profileRoot": path, "profileIdentity": identity,
            "observation_id": native.grokbot_observation_id(path, profile_identity=identity),
            "observation_version": 2, "state": "app-detected",
            "mapping": "workspace-mapping-unavailable",
        } for path, identity in ((moved, self.original_identity), (replacement, self.replacement_identity))]
        locations = {old: self.replacement_identity, moved: self.original_identity, replacement: self.replacement_identity}
        for order in itertools.permutations(observations):
            result = {
                "provider": "grokbot", "catalog": [], "observations": list(order),
                "profileRoots": [moved, replacement],
                "profileIdentities": {moved: self.original_identity, replacement: self.replacement_identity},
            }
            with self.subTest(order=[item["profileRoot"] for item in order]):
                with mock.patch.object(manager, "same_location", side_effect=lambda left, right: locations[str(left)] == locations[str(right)]):
                    with self.assertRaisesRegex(fs.RoutingError, "native-identity-ambiguous"):
                        manager.remap_native_identities(state, result)
            self.assertEqual(state["forgotten"], [legacy])
            self.assertEqual(state["selected"], [])

    def test_refresh_rejection_preserves_original_suppression_for_each_order(self):
        with fixture_directory() as root:
            workspace = root / "manager"
            args = manager.parser().parse_args(["init", "--workspace", str(workspace), "--owner", "synthetic"])
            with mock.patch.object(manager, "find_rapp1", return_value=root):
                with mock.patch.object(manager, "load_rapp", return_value=FakeRapp):
                    with contextlib.redirect_stdout(io.StringIO()):
                        args.run(args)
            old, moved, replacement = (root / "profiles" / name for name in ("A", "B", "a"))

            def create_profile(path):
                file = path / "session-state" / session_id() / "workspace.yaml"
                file.parent.mkdir(parents=True)
                file.write_text(f"id: {session_id()}\ncwd: null\n")

            create_profile(old)
            manager.refresh_provider(workspace, "copilot", [old])
            registry = manager.load_registry(workspace)
            original_identity = registry["providers"]["copilot"]["profileIdentities"][str(old)]
            legacy = native.legacy_pointer_id("copilot", old, "copilot-session", session_id())
            registry["providers"]["copilot"].update(catalog=[], selected=[], forgotten=[legacy])
            manager.save_registry(workspace, manager.manager_identity(workspace), registry)
            original_state = copy.deepcopy(registry["providers"]["copilot"])
            old.rename(moved)
            create_profile(replacement)
            replacement_identity = fs.directory_identity(replacement)
            location_ids = {
                str(old): replacement_identity, str(replacement): replacement_identity,
                str(moved): original_identity,
            }
            before_native = snapshot(moved), snapshot(replacement)
            real_scan = native.scan_provider
            for order in ((moved, replacement), (replacement, moved)):
                def ordered_scan(*args, **kwargs):
                    result = real_scan(*args, **kwargs)
                    items = {item["profileRoot"]: item for item in result["catalog"]}
                    result["catalog"] = [items[str(path)] for path in order]
                    return result
                with self.subTest(order=order):
                    with mock.patch.object(native, "scan_provider", side_effect=ordered_scan):
                        with mock.patch.object(manager, "same_location", side_effect=lambda left, right: location_ids[str(left)] == location_ids[str(right)]):
                            result = manager.refresh_provider(workspace, "copilot", [moved, replacement])
                    self.assertEqual(result["status"], "stale")
                    self.assertEqual(result["error"], "native-identity-ambiguous")
                    state = manager.load_registry(workspace)["providers"]["copilot"]
                    for field in ("catalog", "forgotten", "selected", "profileRoots", "profileIdentities", "profileHistory", "last_success_utc"):
                        self.assertEqual(state[field], original_state[field])
                    self.assertIsNone(state["pending"])
                    self.assertEqual((snapshot(moved), snapshot(replacement)), before_native)


if __name__ == "__main__":
    unittest.main()
