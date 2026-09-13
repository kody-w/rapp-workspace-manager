import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import native_ai as native
import routing_io as fs
import workspace_manager as manager
from support import fixture_directory, metadata_guard, snapshot, write_json
from test_federation import FakeRapp
from test_native_ai import session_id


class MediumRegressionTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_directory()
        self.root = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.workspace = self.root / "manager"
        self.command("init", "--workspace", self.workspace, "--owner", "synthetic")

    def command(self, *args):
        parsed = manager.parser().parse_args(list(map(str, args)))
        with mock.patch.object(manager, "find_rapp1", return_value=self.root):
            with mock.patch.object(manager, "load_rapp", return_value=FakeRapp):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    parsed.run(parsed)
        return output.getvalue()

    def folder(self, relative):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copilot(self, root=None, cwd=None, number=1):
        root = root or self.root / "profiles/NativeProfile"
        file = root / "session-state" / session_id(number) / "workspace.yaml"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"id: {session_id(number)}\ncwd: {json.dumps(str(cwd)) if cwd else 'null'}\n")
        return root, file

    def registry(self):
        return manager.load_registry(self.workspace)

    def state(self, provider="copilot"):
        return self.registry()["providers"][provider]

    def folders(self):
        return json.loads((self.workspace / "estate.code-workspace").read_text())["folders"]

    def historical_scout(self):
        healthy = self.folder("source/healthy")
        self.command("estate", "--workspace", self.workspace, "--root", healthy)
        old = self.folder("profiles/FormerProfile")
        write_json(old / "m-sessions/workspaces.json", {"version": 3, "workspaces": []})
        manager.refresh_provider(self.workspace, "scout", [old])
        current = old.with_name("CurrentProfile")
        old.rename(current)
        manager.refresh_provider(self.workspace, "scout", [current])
        return healthy, old, current

    def test_reused_profile_path_never_transfers_or_consumes_original_forget(self):
        source = self.folder("source/project")
        original, _ = self.copilot(cwd=source)
        manager.refresh_provider(self.workspace, "copilot", [original])
        original_id = self.state()["catalog"][0]["pointer_id"]
        manager.provider_action(self.workspace, "copilot", "forget", original_id)
        parked_original = original.with_name("ParkedOriginal")
        original.rename(parked_original)
        replacement, _ = self.copilot(original, source)
        replacement_id = native.pointer_id("copilot", replacement, "copilot-session", session_id())
        self.assertNotEqual(original_id, replacement_id)
        before = snapshot(parked_original), snapshot(replacement)
        manager.refresh_provider(self.workspace, "copilot", [replacement])
        self.assertIn(original_id, self.state()["forgotten"])
        self.assertNotIn(replacement_id, self.state()["forgotten"])
        self.assertEqual(self.state()["selected"], [])
        self.assertEqual((snapshot(parked_original), snapshot(replacement)), before)
        parked_replacement = original.with_name("ParkedReplacement")
        replacement.rename(parked_replacement)
        parked_original.rename(original)
        manager.refresh_provider(self.workspace, "copilot", [original])
        self.assertIn(original_id, self.state()["forgotten"])
        self.assertNotIn(original_id, [item["pointer_id"] for item in self.state()["catalog"]])
        manager.provider_action(self.workspace, "copilot", "re-add", original_id)
        manager.refresh_provider(self.workspace, "copilot", [original])
        self.assertEqual(self.state()["selected"], [original_id])
        self.assertEqual(self.state()["forgotten"], [])

    def test_reused_profile_path_never_inherits_selection_from_conflicting_inode(self):
        source = self.folder("source/project")
        profile, _ = self.copilot(cwd=source)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        old_id = self.state()["catalog"][0]["pointer_id"]
        manager.provider_action(self.workspace, "copilot", "select", old_id)
        profile.rename(profile.with_name("Parked"))
        self.copilot(profile, source)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        new_id = self.state()["catalog"][0]["pointer_id"]
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(self.state()["selected"], [old_id])
        self.assertEqual(len(self.folders()), 1)
        manager.provider_action(self.workspace, "copilot", "re-add", new_id)
        self.assertIn(new_id, self.state()["selected"])
        self.assertEqual(len(self.folders()), 2)

    def test_copilot_cached_alias_rebinds_locator_without_mutating_previous_metadata(self):
        profile, file = self.copilot()
        previous = native.scan_provider("copilot", [profile])["catalog"][0]
        before = copy.deepcopy(previous)
        alias = profile.with_name("nativeprofile")
        with mock.patch.object(native, "safe_stat", return_value=file.stat()):
            with mock.patch.object(native, "read_bytes", side_effect=AssertionError("cached YAML must not be reopened")):
                current, reused = native._copilot_item(
                    alias, session_id(), previous, fs.Budget(), previous["profileIdentity"],
                )
        self.assertTrue(reused)
        self.assertEqual(current["pointer_id"], previous["pointer_id"])
        self.assertEqual(current["profileRoot"], str(alias))
        self.assertEqual(current["profileIdentity"], previous["profileIdentity"])
        self.assertEqual(current["metadata"], previous["metadata"])
        self.assertEqual(previous, before)

    def test_cached_refresh_after_verified_profile_rename_is_fresh_and_stable(self):
        source = self.folder("source/project")
        profile, file = self.copilot(cwd=source)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        key = self.state()["catalog"][0]["pointer_id"]
        manager.provider_action(self.workspace, "copilot", "select", key)
        current = profile.with_name("CurrentAlias")
        profile.rename(current)
        before = snapshot(current)
        with mock.patch.object(native, "read_bytes", side_effect=AssertionError("unchanged YAML must remain cached")):
            result = manager.refresh_provider(self.workspace, "copilot", [current])
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["reused"], 1)
        self.assertEqual(self.state()["catalog"][0]["profileRoot"], str(current))
        self.assertEqual(self.state()["selected"], [key])
        self.assertEqual(snapshot(current), before)

    def test_symlinked_historical_locator_does_not_hide_unrelated_routes(self):
        healthy, old, current = self.historical_scout()
        forbidden = self.folder("do-not-follow")
        (forbidden / "credentials").write_text("FORBIDDEN")
        old.symlink_to(forbidden, target_is_directory=True)
        before = snapshot(current), snapshot(forbidden), snapshot(healthy)
        with metadata_guard([current, forbidden, healthy], []):
            self.command("editor-view", "--workspace", self.workspace)
            opened = self.command("open", "--workspace", self.workspace, "--name", "healthy", "--print-path")
        self.assertEqual(opened.strip(), str(healthy))
        self.assertEqual(len(self.folders()), 2)
        self.assertEqual((snapshot(current), snapshot(forbidden), snapshot(healthy)), before)

    def test_inaccessible_historical_locator_isolated_from_healthy_open_and_view(self):
        healthy, old, _ = self.historical_scout()
        real = fs.directory_info

        def lookup(path, *args, **kwargs):
            if fs.absolute_path(path) == old:
                raise fs.RoutingError("metadata-unreadable")
            return real(path, *args, **kwargs)

        with mock.patch.object(fs, "directory_info", side_effect=lookup):
            self.command("editor-view", "--workspace", self.workspace)
            self.assertEqual(
                self.command("open", "--workspace", self.workspace, "--name", "healthy", "--print-path").strip(),
                str(healthy),
            )
        self.assertEqual(len(self.folders()), 2)

    def test_ambiguous_legacy_suppression_requires_explicit_readd_not_guessing(self):
        source = self.folder("source/project")
        profile, _ = self.copilot(cwd=source)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        registry = self.registry()
        state = registry["providers"]["copilot"]
        current_id = state["catalog"][0]["pointer_id"]
        legacy_id = native.legacy_pointer_id("copilot", profile, "copilot-session", session_id())
        device, inode = state["profileIdentities"][str(profile)]
        state["profileHistory"].append({"path": str(profile), "identity": [device, inode + 1]})
        state.update(catalog=[], selected=[], forgotten=[legacy_id])
        manager.save_registry(self.workspace, manager.manager_identity(self.workspace), registry)
        result = manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["error"], "native-identity-ambiguous")
        self.assertEqual(self.state()["forgotten"], [legacy_id])
        manager.provider_action(self.workspace, "copilot", "re-add", legacy_id)
        manager.refresh_provider(self.workspace, "copilot")
        self.assertNotIn(current_id, self.state()["selected"])
        self.assertEqual(len(self.folders()), 1)
        manager.provider_action(self.workspace, "copilot", "re-add", current_id)
        self.assertIn(current_id, self.state()["selected"])
        self.assertEqual(len(self.folders()), 2)

    def test_legacy_ambiguity_is_scoped_to_the_affected_profile(self):
        profile, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [profile])
        registry = self.registry()
        state = registry["providers"]["copilot"]
        legacy_id = native.legacy_pointer_id("copilot", profile, "copilot-session", session_id())
        device, inode = state["profileIdentities"][str(profile)]
        state["profileHistory"].append({"path": str(profile), "identity": [device, inode + 1]})
        state.update(catalog=[], selected=[], forgotten=[legacy_id])
        manager.save_registry(self.workspace, manager.manager_identity(self.workspace), registry)
        unrelated, _ = self.copilot(self.root / "profiles/Unrelated")
        result = manager.refresh_provider(self.workspace, "copilot", [unrelated])
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(self.state()["forgotten"], [legacy_id])
        self.assertEqual(self.state()["catalog"][0]["profileRoot"], str(unrelated))

    def test_grok_observation_forget_survives_conflicting_profile_replacement(self):
        original = self.folder("Grokbot.app")
        manager.refresh_provider(self.workspace, "grokbot", [original])
        original_id = self.state("grokbot")["observations"][0]["observation_id"]
        manager.provider_action(self.workspace, "grokbot", "forget", original_id)
        parked = original.with_name("SavedOriginal")
        original.rename(parked)
        original.mkdir()
        manager.refresh_provider(self.workspace, "grokbot", [original])
        self.assertIn(original_id, self.state("grokbot")["forgotten"])
        self.assertEqual(self.state("grokbot")["selected"], [])
        original.rename(original.with_name("SavedReplacement"))
        parked.rename(original)
        manager.refresh_provider(self.workspace, "grokbot", [original])
        self.assertEqual(self.state("grokbot")["observations"], [])
        self.assertEqual(self.state("grokbot")["forgotten"], [original_id])

    def test_cached_locator_rebinding_is_consistent_across_batched_refresh(self):
        profile, _ = self.copilot()
        self.copilot(profile, number=2)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        ids = {item["pointer_id"] for item in self.state()["catalog"]}
        alias = profile.with_name("RenamedProfile")
        profile.rename(alias)
        with mock.patch.object(native, "read_bytes", side_effect=AssertionError("cache should be reused")):
            first = manager.refresh_provider(self.workspace, "copilot", [alias], fs.Limits(batch_size=1))
            self.assertEqual(first["status"], "refreshing")
            self.assertEqual(self.state()["pending"]["catalog"][0]["profileRoot"], str(alias))
            second = manager.refresh_provider(self.workspace, "copilot", limits=fs.Limits(batch_size=1))
        self.assertEqual(second["status"], "fresh")
        self.assertEqual({item["pointer_id"] for item in self.state()["catalog"]}, ids)
        self.assertTrue(all(item["profileRoot"] == str(alias) for item in self.state()["catalog"]))

    def test_unexpected_cached_namespace_becomes_stale_not_keyerror(self):
        profile, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [profile])
        before = self.state()
        real = native._copilot_item

        def wrong_namespace(*args, **kwargs):
            item, reused = real(*args, **kwargs)
            return {**item, "profileRoot": str(self.root / "not-requested")}, reused

        with mock.patch.object(native, "_copilot_item", side_effect=wrong_namespace):
            result = manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["error"], "metadata-changed")
        self.assertEqual(self.state()["catalog"], before["catalog"])
        self.assertEqual(self.state()["last_success_utc"], before["last_success_utc"])

    def test_reused_obsolete_locator_does_not_claim_the_new_occupant_as_native(self):
        healthy, old, current = self.historical_scout()
        old.mkdir()
        (old / ".git").mkdir()
        before = snapshot(old), snapshot(current)
        self.command("estate", "--workspace", self.workspace, "--root", healthy, "--root", old)
        self.assertEqual(len(self.folders()), 3)
        self.assertEqual((snapshot(old), snapshot(current)), before)
        with self.assertRaisesRegex(fs.RoutingError, "native-store-not-workspace"):
            self.command("estate", "--workspace", self.workspace, "--root", current)

    def test_historical_failures_do_not_break_recursive_discovery(self):
        healthy, old, current = self.historical_scout()
        (healthy / ".git").mkdir()
        forbidden = self.folder("do-not-follow")
        (forbidden / "private.json").write_text("FORBIDDEN")
        old.symlink_to(forbidden, target_is_directory=True)
        with metadata_guard([current, forbidden, healthy], [healthy / "rappid.json"]):
            self.command("scan", "--workspace", self.workspace, "--root", healthy.parent)
        self.assertEqual(len(self.folders()), 2)

    def test_verified_current_locator_retains_native_inode_and_ancestor_protection(self):
        healthy, old, current = self.historical_scout()
        nested = current / "private-child"
        nested.mkdir()
        old.symlink_to(self.folder("unrelated-target"), target_is_directory=True)
        boundaries = manager.all_profile_boundaries(self.registry())
        self.assertTrue(fs.protected_local(current, boundaries))
        self.assertTrue(fs.protected_local(nested, boundaries))
        self.assertTrue(fs.protected_local(current.parent, boundaries))
        self.assertFalse(fs.protected_local(healthy, boundaries))
        with self.assertRaisesRegex(fs.RoutingError, "native-store-not-workspace"):
            self.command("estate", "--workspace", self.workspace, "--root", nested)


if __name__ == "__main__":
    unittest.main()
