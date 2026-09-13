import contextlib
import copy
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import native_ai as native
import routing_io as fs
import workspace_manager as manager
from support import fixture_directory, metadata_guard, snapshot
from test_federation import FakeRapp
from test_native_ai import session_id


class ReviewedBoundaryRegressions(unittest.TestCase):
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
                with contextlib.redirect_stdout(io.StringIO()):
                    return parsed.run(parsed)

    def folder(self, relative):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copilot(self, cwd=None, profile="profiles/Copilot"):
        root = self.folder(profile)
        file = root / "session-state" / session_id() / "workspace.yaml"
        file.parent.mkdir(parents=True)
        file.write_text(f"id: {session_id()}\ncwd: {json.dumps(str(cwd)) if cwd else 'null'}\n")
        return root, file

    def registry(self):
        return manager.load_registry(self.workspace)

    def save(self, registry):
        manager.save_registry(self.workspace, manager.manager_identity(self.workspace), registry)

    def folders(self):
        return json.loads((self.workspace / "estate.code-workspace").read_text())["folders"]

    def legacy_copilot(self, profile, file, cwd):
        return {
            "pointer_version": 1, "pointer_type": "copilot-session",
            "pointer_id": native.legacy_pointer_id("copilot", profile, "copilot-session", session_id()),
            "provider": "copilot", "profileRoot": str(profile),
            "nativeSessionId": session_id(), "availability": "metadata",
            "sourceStamp": fs.stamp(file.stat()),
            "metadata": {"id": session_id(), "cwd": str(cwd)},
        }

    def seed_legacy_provider(self, root, item, *, selected=False, forgotten=False):
        registry = self.registry()
        state = manager.empty_provider()
        state.update(
            profileRoots=[str(root)], requestedRoots=[str(root)], status="fresh",
            last_success_utc="2026-01-01T00:00:00.000Z",
            catalog=[] if forgotten else [item],
            selected=[item["pointer_id"]] if selected else [],
            forgotten=[item["pointer_id"]] if forgotten else [],
        )
        registry["providers"]["copilot"] = state
        self.save(registry)

    def test_ignored_multiline_quoted_summary_cannot_supply_cwd(self):
        source = self.folder("source/project")
        profile, file = self.copilot(source)
        before_source = snapshot(source)
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                file.write_text(
                    f"id: {session_id()}\nsummary: {quote}first line\n"
                    f"cwd: {source}\nlast line{quote}\n"
                )
                before_native = snapshot(profile)
                with metadata_guard([profile, source], [file]):
                    with self.assertRaisesRegex(fs.RoutingError, "schema-mismatch"):
                        native.scan_provider("copilot", [profile])
                    result = manager.refresh_provider(self.workspace, "copilot", [profile])
                self.assertEqual(result["status"], "stale")
                self.assertEqual(self.registry()["providers"]["copilot"]["catalog"], [])
                self.assertEqual(len(self.folders()), 1)
                self.assertEqual(snapshot(profile), before_native)
        self.assertEqual(snapshot(source), before_source)

    def test_unknown_yaml_structures_fail_closed_instead_of_scanning_continuations(self):
        for ignored in (
            'summary: [first line,\ncwd: /not-a-metadata-key\n]\n',
            'summary: {nested:\ncwd: /not-a-metadata-key\n}\n',
            'summary: &anchor "first line\ncwd: /not-a-metadata-key\nlast"\n',
            'summary: !!str "first line\ncwd: /not-a-metadata-key\nlast"\n',
            'summary: *alias\ncwd: /not-authorized\n',
            'summary: plain\n  cwd: /continuation\n',
            'summary: "closed" invalid-tail\ncwd: /not-authorized\n',
            'summary: "closed"#not-a-separated-comment\ncwd: /not-authorized\n',
            'summary: @unsupported\ncwd: /not-authorized\n',
            'summary: - unsupported-sequence\ncwd: /not-authorized\n',
            'summary: nested:\tvalue\ncwd: /not-authorized\n',
            'summary: one\nsummary: two\n',
            'summary: one\n---\ncwd: /second-document\n',
            '"summary": "first line\ncwd: /continuation\nlast"\n',
        ):
            with self.subTest(ignored=ignored), self.assertRaises(fs.RoutingError):
                native._yaml_metadata(f"id: {session_id()}\n{ignored}".encode())

    def test_ignored_block_scalars_stay_opaque_and_scalar_metadata_still_works(self):
        raw = (
            f"---\nid: {session_id()}\nsummary: |-\n"
            "  cwd: /forbidden-block-content\n"
            "  id: not-the-native-id\n"
            "  summary: \"unterminated text inside an opaque block\n"
            "branch: 'feature/fix'\n"
            'description: "escaped \\"quote\\" and \\\\ slash"\n'
            "cwd: '/synthetic/project'\n...\n"
        ).encode()
        metadata = native._yaml_metadata(raw)
        self.assertEqual(metadata, {
            "id": session_id(), "branch": "feature/fix", "cwd": "/synthetic/project",
        })
        self.assertNotIn("forbidden", json.dumps(metadata))

    def test_non_yaml_line_separators_cannot_introduce_metadata_keys(self):
        for separator in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
            with self.subTest(separator=repr(separator)), self.assertRaises(fs.RoutingError):
                native._yaml_metadata(
                    f"id: {session_id()}\nsummary: first{separator}cwd: /not-metadata\n".encode()
                )
        self.assertEqual(
            native._yaml_metadata(f"id: {session_id()}\r\ncwd: null\r\n".encode())["cwd"],
            None,
        )
        literal = "/synthetic/project/\u00a0#literal"
        self.assertEqual(
            native._yaml_metadata(f"id: {session_id()}\ncwd: {literal}\n".encode())["cwd"],
            literal,
        )

    def test_inherited_v1_poisoned_cache_is_quarantined_and_must_be_reparsed(self):
        source = self.folder("source/project")
        profile, file = self.copilot(source)
        file.write_text(
            f'id: {session_id()}\nsummary: "first line\ncwd: {source}\nlast line"\n'
        )
        legacy = self.legacy_copilot(profile, file, source)
        self.seed_legacy_provider(profile, legacy, selected=True)
        self.assertEqual(native.local_paths(legacy), [])
        self.assertEqual(len(self.folders()), 1)
        with mock.patch.object(native, "read_bytes", wraps=native.read_bytes) as reads:
            result = manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(result["status"], "stale")
        state = self.registry()["providers"]["copilot"]
        self.assertEqual(state["catalog"], [legacy])
        self.assertEqual(state["last_success_utc"], "2026-01-01T00:00:00.000Z")
        self.assertEqual(len(self.folders()), 1)

    def test_inherited_v1_checkpoint_cannot_reintroduce_poisoned_metadata(self):
        source = self.folder("source/project")
        profile, file = self.copilot(source)
        file.write_text(
            f'id: {session_id()}\nsummary: "first line\ncwd: {source}\nlast line"\n'
        )
        legacy = self.legacy_copilot(profile, file, source)
        pending = {
            "version": 1,
            "inventories": [{
                "profileRoot": str(profile),
                "stamp": fs.stamp((profile / "session-state").stat()),
                "names": [session_id()],
            }],
            "profile_index": 0, "offset": 1, "catalog": [legacy],
        }
        with mock.patch.object(native, "read_bytes", wraps=native.read_bytes) as reads:
            with self.assertRaisesRegex(fs.RoutingError, "schema-mismatch"):
                native.scan_provider("copilot", [profile], previous=[legacy], pending=pending)
        self.assertEqual(reads.call_count, 1)

    def test_valid_v1_cache_upgrade_preserves_selection_only_after_full_safe_scan(self):
        source = self.folder("source/project")
        profile, file = self.copilot(source)
        legacy = self.legacy_copilot(profile, file, source)
        self.seed_legacy_provider(profile, legacy, selected=True)
        result = manager.refresh_provider(self.workspace, "copilot")
        state = self.registry()["providers"]["copilot"]
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(state["catalog"][0]["pointer_version"], 2)
        self.assertEqual(state["selected"], [state["catalog"][0]["pointer_id"]])
        self.assertNotEqual(state["selected"], [legacy["pointer_id"]])
        self.assertEqual(len(self.folders()), 2)

    def test_all_leading_slash_aliases_share_one_normalized_path_and_pointer_id(self):
        source = self.folder("source/project")
        key = manager.local_id(source)
        for number in range(2, 9):
            alias = "/" * number + str(source).lstrip("/")
            with self.subTest(slashes=number):
                self.assertEqual(fs.absolute_path(alias), source)
                self.assertEqual(manager.local_id(alias), key)
        self.command(
            "estate", "--workspace", self.workspace, "--root", source,
            "--root", "//" + str(source).lstrip("/"),
        )
        self.assertEqual(len(self.registry()["workspaces"]), 1)
        self.assertEqual(len(self.folders()), 2)
        with self.assertRaisesRegex(fs.RoutingError, "path-traversal"):
            fs.absolute_path(str(source) + "/../escape")

    def test_home_aliases_and_home_ancestors_never_become_editor_roots(self):
        home = self.folder("ProtectedHome")
        (home / "credentials").write_text("FORBIDDEN")
        aliases = [str(home), "//" + str(home).lstrip("/"), "////" + str(home).lstrip("/")]
        case_alias = home.with_name("protectedhome")
        if case_alias.is_dir():
            aliases.append(str(case_alias))
        before = snapshot(home)
        with mock.patch.object(fs.Path, "home", return_value=home):
            with metadata_guard([home], []):
                for alias in aliases:
                    with self.subTest(alias=alias):
                        self.assertIsNone(fs.verified_directory(alias))
                        with self.assertRaises(fs.RoutingError):
                            self.command("estate", "--workspace", self.workspace, "--root", alias)
                        with self.assertRaises(fs.RoutingError):
                            manager.discover_git_workspaces(alias)
                        with self.assertRaisesRegex(fs.RoutingError, "broad-native-root"):
                            native.scan_provider("copilot", [alias])
                self.assertIsNone(fs.verified_directory(str(home.parent)))
        self.assertEqual(snapshot(home), before)
        self.assertEqual(len(self.folders()), 1)

    def test_legacy_double_slash_home_pointer_is_not_projected(self):
        home = self.folder("ProtectedHome")
        alias = "//" + str(home).lstrip("/")
        registry = self.registry()
        registry["workspaces"] = [{
            "name": "unsafe legacy route", "path": alias, "kind": "directory",
            "mode": None, "world_id": None, "rappid": None, "tags": [],
            "pointer_version": 1, "pointer_type": "local-directory",
            "pointer_id": manager.legacy_local_id(alias), "selection": "exact",
        }]
        with mock.patch.object(fs.Path, "home", return_value=home), metadata_guard([home], []):
            self.save(registry)
        self.assertEqual(len(self.folders()), 1)

    def test_case_behavior_is_volume_identity_driven_not_global_casefold(self):
        records = {
            "/insensitive/Project": ([10, 7], [[10, 7], [10, 1]]),
            "/insensitive/project": ([10, 7], [[10, 7], [10, 1]]),
            "/sensitive/Project": ([20, 7], [[20, 7], [20, 1]]),
            "/sensitive/project": ([20, 8], [[20, 8], [20, 1]]),
        }

        def info(path, **kwargs):
            key, ancestors = records[str(path)]
            return {"path": str(path), "identity": key, "ancestors": ancestors}

        with mock.patch.object(fs, "directory_info", side_effect=info):
            self.assertTrue(fs.same_directory("/insensitive/Project", "/insensitive/project"))
            self.assertFalse(fs.same_directory("/sensitive/Project", "/sensitive/project"))
            self.assertFalse(fs.directories_overlap("/sensitive/Project", "/sensitive/project"))
            self.assertFalse(fs.same_directory("/insensitive/Project", "/sensitive/Project"))
        with mock.patch.object(native, "directory_identity", side_effect=lambda path: info(path)["identity"]):
            self.assertEqual(manager.local_id("/insensitive/Project"), manager.local_id("/insensitive/project"))
            self.assertNotEqual(manager.local_id("/sensitive/Project"), manager.local_id("/sensitive/project"))
            self.assertNotEqual(manager.local_id("/insensitive/Project"), manager.local_id("/sensitive/Project"))

    def test_kernel_ancestry_protects_aliases_without_lexical_prefixes(self):
        records = {
            "/visible-alias": ([30, 50], [[30, 50], [30, 20], [30, 1]]),
            "/protected-native": ([30, 20], [[30, 20], [30, 1]]),
            "/owner-home": ([30, 90], [[30, 90], [30, 1]]),
        }

        def info(path, **kwargs):
            identity, ancestors = records[str(path)]
            return {"path": str(path), "identity": identity, "ancestors": ancestors}

        with mock.patch.object(fs, "directory_info", side_effect=info):
            with mock.patch.object(fs.Path, "home", return_value=Path("/owner-home")):
                self.assertTrue(fs.protected_local("/visible-alias", ["/protected-native"]))
                self.assertTrue(fs.directories_overlap("/visible-alias", "/protected-native"))
        actual = self.folder("actual/parent/child")
        info = fs.directory_info(actual)
        self.assertEqual(info["identity"], fs.directory_identity(actual))
        self.assertEqual(info["ancestors"][1], fs.directory_identity(actual.parent))

    def test_case_alias_dedupe_forget_and_readd_on_the_host_volume(self):
        source = self.folder("CaseProject")
        alias = source.with_name("caseproject")
        insensitive = alias.is_dir()
        if not insensitive:
            alias.mkdir()
        (source / "SOURCE-CANARY").write_text("FORBIDDEN")
        before = snapshot(source), snapshot(alias)
        self.command("estate", "--workspace", self.workspace, "--root", source, "--root", alias)
        expected = 1 if insensitive else 2
        self.assertEqual(len(self.registry()["workspaces"]), expected)
        original_id = manager.local_id(source)
        self.command("forget", "--workspace", self.workspace, "--path", alias if insensitive else source)
        self.command("estate", "--workspace", self.workspace, "--root", alias)
        self.assertEqual(len(self.registry()["workspaces"]), 0 if insensitive else 1)
        self.command("re-add", "--workspace", self.workspace, "--path", alias if insensitive else source)
        self.assertIn(original_id, [item["pointer_id"] for item in self.registry()["workspaces"]])
        self.assertEqual((snapshot(source), snapshot(alias)), before)

    def test_forget_tracks_inode_moves_and_recreated_original_location(self):
        source = self.folder("source/original")
        (source / "SOURCE-CANARY").write_text("FORBIDDEN")
        self.command("estate", "--workspace", self.workspace, "--root", source)
        original_id = self.registry()["workspaces"][0]["pointer_id"]
        self.command("forget", "--workspace", self.workspace, "--path", source)
        moved = source.with_name("renamed")
        source.rename(moved)
        source.mkdir()
        self.command("estate", "--workspace", self.workspace, "--root", moved, "--root", source)
        self.assertEqual(self.registry()["workspaces"], [])
        self.assertEqual(len(self.folders()), 1)
        self.command("re-add", "--workspace", self.workspace, "--path", moved)
        self.assertEqual(self.registry()["workspaces"][0]["pointer_id"], original_id)
        self.assertEqual(self.registry()["forgotten"], [])
        self.assertEqual((moved / "SOURCE-CANARY").read_text(), "FORBIDDEN")

    def test_replaced_local_directory_cannot_silently_reanchor_existing_pointer(self):
        source = self.folder("source/project")
        self.command("estate", "--workspace", self.workspace, "--root", source)
        old = self.registry()["workspaces"][0]
        source.rename(source.with_name("previous"))
        source.mkdir()
        self.command("editor-view", "--workspace", self.workspace)
        self.assertEqual(len(self.folders()), 1)
        self.assertEqual(self.registry()["workspaces"], [old])
        with self.assertRaisesRegex(fs.RoutingError, "local-route-unavailable"):
            self.command("open", "--workspace", self.workspace, "--name", "project", "--print-path")
        self.command("re-add", "--workspace", self.workspace, "--path", source)
        self.assertNotEqual(self.registry()["workspaces"][0]["pointer_id"], old["pointer_id"])

    def test_manager_alias_overlap_and_parent_overlap_fail_closed(self):
        double = "//" + str(self.workspace).lstrip("/")
        aliases = [double]
        case_alias = self.workspace.with_name("MANAGER")
        if case_alias.is_dir():
            aliases.append(str(case_alias))
        for alias in aliases:
            with self.subTest(alias=alias):
                self.command("estate", "--workspace", self.workspace, "--root", alias)
                self.assertEqual(self.registry()["workspaces"], [])
                self.assertEqual(len(self.folders()), 1)
                with self.assertRaisesRegex(fs.RoutingError, "manager-native-overlap"):
                    manager.refresh_provider(self.workspace, "copilot", [alias])
                with self.assertRaisesRegex(fs.RoutingError, "manager-route-overlap"):
                    manager.check_route_boundary(self.workspace, alias, self.registry())
        with self.assertRaisesRegex(fs.RoutingError, "manager-route-overlap"):
            manager.check_route_boundary(self.workspace, self.root, self.registry())
        with self.assertRaisesRegex(fs.RoutingError, "manager-route-overlap"):
            manager.check_route_boundary(self.workspace, self.workspace / "projects", self.registry())

    def test_native_manager_overlap_is_refused_before_creating_any_manager_lock(self):
        lock = self.workspace / ".routing.lock"
        self.assertFalse(lock.exists())
        before = snapshot(self.workspace)
        with metadata_guard([self.workspace], [self.workspace / "rappid.json", self.workspace / "registry.json"]):
            with self.assertRaisesRegex(fs.RoutingError, "manager-native-overlap"):
                manager.refresh_provider(
                    self.workspace, "copilot", ["//" + str(self.workspace).lstrip("/")],
                )
        self.assertEqual(snapshot(self.workspace), before)
        self.assertFalse(lock.exists())

    def test_native_profile_alias_identity_suppression_and_readd(self):
        source = self.folder("source/project")
        profile, file = self.copilot(source)
        alias = profile.with_name("copilot")
        if not alias.is_dir():
            alias = Path("//" + str(profile).lstrip("/"))
        first = native.scan_provider("copilot", [profile, alias])
        self.assertEqual(len(first["catalog"]), 1)
        self.assertEqual(len(first["profileRoots"]), 1)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        key = self.registry()["providers"]["copilot"]["catalog"][0]["pointer_id"]
        before = snapshot(profile)
        with metadata_guard([profile, alias, source], [file, alias / "session-state" / session_id() / "workspace.yaml"]):
            manager.provider_action(self.workspace, "copilot", "forget", key)
            manager.refresh_provider(self.workspace, "copilot", [alias])
            self.assertEqual(self.registry()["providers"]["copilot"]["catalog"], [])
            manager.provider_action(self.workspace, "copilot", "re-add", key)
            manager.refresh_provider(self.workspace, "copilot", [alias])
        state = self.registry()["providers"]["copilot"]
        self.assertEqual(state["selected"], [key])
        self.assertEqual(state["catalog"][0]["pointer_id"], key)
        self.assertEqual(snapshot(profile), before)

    def test_native_root_move_stays_protected_and_recursive_scan_does_not_enter_it(self):
        profile, file = self.copilot()
        (file.parent / ".git").mkdir()
        manager.refresh_provider(self.workspace, "copilot", [profile])
        moved = profile.with_name("renamed-profile")
        profile.rename(moved)
        with self.assertRaisesRegex(fs.RoutingError, "native-store-not-workspace"):
            self.command("estate", "--workspace", self.workspace, "--root", moved)
        with metadata_guard([moved], []):
            self.command("scan", "--workspace", self.workspace, "--root", moved.parent)
        self.assertEqual(self.registry()["workspaces"], [])
        self.assertEqual(len(self.registry()["providers"]["copilot"]["catalog"]), 1)

    def test_metadata_and_manager_hardlinks_are_refused_before_content_read_or_write(self):
        profile, file = self.copilot()
        other = self.root / "private-original"
        file.rename(other)
        os.link(other, file)
        before = other.read_bytes()
        with mock.patch.object(fs.os, "read", side_effect=AssertionError("hardlinked contents must not be read")):
            with self.assertRaisesRegex(fs.RoutingError, "hardlink-refused"):
                native.scan_provider("copilot", [profile])
        for filename in ("estate.code-workspace", ".routing.lock"):
            target = self.workspace / filename
            target.unlink(missing_ok=True)
            os.link(other, target)
            with self.subTest(filename=filename), self.assertRaisesRegex(fs.RoutingError, "hardlink-refused"):
                if filename == ".routing.lock":
                    with fs.manager_lock(self.workspace):
                        self.fail("hardlinked manager lock acquired")
                else:
                    fs.atomic_json(target, {"folders": []})
            target.unlink()
        self.assertEqual(other.read_bytes(), before)
        self.assertEqual(file.read_bytes(), before)

    def test_hardlinked_root_identity_is_not_a_readable_manager_or_source_identity(self):
        source = self.folder("source/project")
        manager_identity = self.workspace / "rappid.json"
        os.link(manager_identity, source / "rappid.json")
        before = manager_identity.read_bytes()
        with self.assertRaisesRegex(fs.RoutingError, "hardlink-refused"):
            manager.manager_identity(self.workspace)
        pointer = manager.read_workspace_pointer(source, FakeRapp, exact=True)
        self.assertIsNone(pointer["rappid"])
        self.assertEqual(pointer["kind"], "directory")
        self.assertEqual(manager_identity.read_bytes(), before)

    def test_symlink_aliases_remain_refused_even_when_the_inode_would_match(self):
        source = self.folder("source/project")
        alias = self.root / "linked-project"
        alias.symlink_to(source, target_is_directory=True)
        self.assertIsNone(fs.verified_directory(str(alias)))
        with self.assertRaises(fs.RoutingError):
            manager.local_id(alias)
        with self.assertRaises(fs.RoutingError):
            self.command("estate", "--workspace", self.workspace, "--root", alias)
        parent_alias = self.root / "linked-parent"
        parent_alias.symlink_to(source.parent, target_is_directory=True)
        with self.assertRaises(fs.RoutingError):
            fs.directory_identity(parent_alias / "project")

    def test_legacy_local_suppression_is_fail_closed_until_explicit_original_readd(self):
        source = self.folder("source/project")
        original = "//" + str(source).lstrip("/")
        registry = self.registry()
        registry["forgotten"] = [manager.legacy_local_id(original)]
        self.save(registry)
        with self.assertRaisesRegex(fs.RoutingError, "legacy-suppression-readd-required"):
            self.command("estate", "--workspace", self.workspace, "--root", source)
        unrelated = self.folder("source/unrelated")
        with self.assertRaisesRegex(fs.RoutingError, "legacy-suppression-readd-required"):
            self.command("re-add", "--workspace", self.workspace, "--path", unrelated)
        self.command("re-add", "--workspace", self.workspace, "--path", original)
        self.assertEqual(self.registry()["forgotten"], [])
        self.assertEqual(self.registry()["workspaces"][0]["pointer_version"], 2)

    def test_legacy_native_suppression_survives_v2_upgrade_and_explicit_readd(self):
        source = self.folder("source/project")
        profile, file = self.copilot(source)
        legacy = self.legacy_copilot(profile, file, source)
        self.seed_legacy_provider(profile, legacy, forgotten=True)
        result = manager.refresh_provider(self.workspace, "copilot", ["//" + str(profile).lstrip("/")])
        self.assertEqual(result["status"], "fresh")
        state = self.registry()["providers"]["copilot"]
        self.assertEqual(state["catalog"], [])
        self.assertEqual(len(state["forgotten"]), 1)
        key = state["forgotten"][0]
        self.assertNotEqual(key, legacy["pointer_id"])
        manager.provider_action(self.workspace, "copilot", "re-add", key)
        manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(self.registry()["providers"]["copilot"]["selected"], [key])
        self.assertEqual(len(self.folders()), 2)

    def test_registry_validation_uses_saved_identities_without_touching_native_profiles(self):
        profile, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [profile])
        state = copy.deepcopy(self.registry())
        with mock.patch.object(native, "directory_identity", side_effect=AssertionError("native identity probe during validation")):
            manager.validate_registry(state)
        item = state["providers"]["copilot"]["catalog"][0]
        item["profileIdentity"] = [item["profileIdentity"][0], item["profileIdentity"][1] + 1]
        with self.assertRaises(fs.RoutingError):
            manager.validate_registry(state)

    def test_profile_inode_change_during_scan_preserves_last_good_catalog(self):
        profile, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [profile])
        before = self.registry()["providers"]["copilot"]
        real_scan = native._copilot

        def replace_profile(roots, previous, pending, budget):
            result = real_scan(roots, previous, pending, budget)
            profile.rename(profile.with_name("prior-profile"))
            profile.mkdir()
            return result

        with mock.patch.object(native, "_copilot", side_effect=replace_profile):
            result = manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["error"], "metadata-changed")
        self.assertEqual(self.registry()["providers"]["copilot"]["catalog"], before["catalog"])


if __name__ == "__main__":
    unittest.main()
