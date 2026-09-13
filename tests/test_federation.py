import contextlib
import copy
import io
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import native_ai as native
import routing_io
import workspace_manager as manager
from routing_io import Limits, RoutingError
from support import fixture_directory, metadata_guard, snapshot, write_json
from test_native_ai import session_id


class FakeRapp:
    @staticmethod
    def rappid_valid(value):
        return isinstance(value, str) and value.startswith("rappid:@") and len(value.rsplit(":", 1)[-1]) == 64

    @staticmethod
    def mint_rappid(owner, slug):
        return f"rappid:@{owner}/{slug}:" + "a" * 64


class FederationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_directory()
        self.root = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.workspace = self.root / "manager"
        self.command("init", "--workspace", str(self.workspace), "--owner", "example")

    def command(self, *arguments):
        args = manager.parser().parse_args(arguments)
        with mock.patch.object(manager, "find_rapp1", return_value=self.root):
            with mock.patch.object(manager, "load_rapp", return_value=FakeRapp):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    result = args.run(args)
        return result, output.getvalue()

    def folder(self, relative):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copilot(self, number=1, cwd=None, profile="native/copilot"):
        root = self.folder(profile)
        directory = self.folder(f"{profile}/session-state/{session_id(number)}")
        path = directory / "workspace.yaml"
        path.write_text(f"id: {session_id(number)}\ncwd: {json.dumps(str(cwd)) if cwd else 'null'}\n")
        return root, path

    def claude(self, key="opaque", cwd=None):
        root = self.folder("native/claude")
        path = write_json(root / "projects" / key / "sessions-index.json", {
            "version": 1, "originalPath": str(cwd) if cwd else None, "entries": [],
        })
        return root, path

    def scout(self, entries=None):
        root = self.folder("native/scout")
        path = write_json(root / "m-sessions/workspaces.json", {
            "version": 3, "workspaces": entries or [
                {"id": "cloud", "providerId": "odsp", "rootId": "opaque:root"}
            ],
        })
        return root, path

    def state(self, provider):
        return manager.load_registry(self.workspace)["providers"][provider]

    def view(self):
        registry = manager.load_registry(self.workspace)
        return json.loads((self.workspace / registry["editor_view"]).read_text())

    def test_init_private_guard_mint_once_and_installed_modules_work(self):
        self.assertIn("PRIVATE / NEVER PUBLISH", (self.workspace / "README.md").read_text())
        self.assertEqual(len(self.view()["folders"]), 1)
        self.assertEqual(self.view()["folders"][0]["path"], str(self.workspace))
        for name in ("workspace_manager.py", "native_ai.py", "routing_io.py"):
            self.assertTrue((self.workspace / "tools" / name).is_file())
        self.assertTrue((self.workspace / "rapp-projects/tools/append_frame.py").is_file())
        with self.assertRaisesRegex(RoutingError, "empty-private"):
            self.command("init", "--workspace", str(self.workspace), "--owner", "example")
        run = subprocess.run(
            [sys.executable, "-B", str(self.workspace / "tools/workspace_manager.py"), "list", "--workspace", str(self.workspace)],
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_exact_synthetic_13_roots_manager_first_no_nested_registration_or_copy(self):
        fixture = json.loads((Path(__file__).parents[1] / "examples/estate-13.synthetic.json").read_text())
        roots = [self.root / item["relativePath"] for item in fixture["roots"]]
        allowed = []
        for index, path in enumerate(roots[1:]):
            path.mkdir()
            (path / "SOURCE-CANARY").write_text("FORBIDDEN-SOURCE")
            if index % 2:
                (path / ".git").mkdir()
            (path / "nested-git" / ".git").mkdir(parents=True)
            allowed.append(path / "rappid.json")
        before = {str(path): snapshot(path) for path in roots[1:]}
        args = ["estate", "--workspace", str(self.workspace)]
        for path in roots:
            args.extend(["--root", str(path)])
        with metadata_guard(roots[1:], allowed):
            self.command(*args)
        view = self.view()
        self.assertEqual(len(view["folders"]), 13)
        self.assertEqual([item["path"] for item in view["folders"]], list(map(str, roots)))
        self.assertEqual([item["name"] for item in view["folders"]], [item["name"] for item in fixture["roots"]])
        registry = manager.load_registry(self.workspace)
        self.assertEqual(len(registry["workspaces"]), 12)
        self.assertEqual(registry["workspaces"][0]["kind"], "directory")
        self.assertTrue(all(item["selection"] == "exact" for item in registry["workspaces"]))
        self.assertNotIn("FORBIDDEN-SOURCE", (self.workspace / "registry.json").read_text())
        self.assertEqual(before, {str(path): snapshot(path) for path in roots[1:]})
        self.assertFalse(any(path.name.startswith("Project") for path in self.workspace.iterdir()))

    def test_recursive_git_nested_worktree_discovery_coexists_with_exact_and_provider_selection(self):
        exact = self.folder("sources/non-git")
        repo = self.folder("sources/repo")
        nested = self.folder("sources/repo/nested")
        worktree = self.folder("sources/worktree")
        for path in (repo, nested):
            (path / ".git").mkdir()
        (worktree / ".git").write_text("FORBIDDEN gitdir: outside")
        root, metadata = self.copilot(cwd=exact)
        manager.refresh_provider(self.workspace, "copilot", [root])
        key = self.state("copilot")["catalog"][0]["pointer_id"]
        manager.provider_action(self.workspace, "copilot", "select", key)
        selected_state = self.state("copilot")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(exact))
        with metadata_guard([self.root / "sources", root], [p / "rappid.json" for p in (exact, repo, nested, worktree)]):
            self.command("scan", "--workspace", str(self.workspace), "--root", str(self.root / "sources"))
        paths = [item["path"] for item in manager.load_registry(self.workspace)["workspaces"]]
        self.assertEqual(set(paths), set(map(str, (exact, repo, nested, worktree))))
        self.assertEqual(self.state("copilot"), selected_state)
        self.assertEqual(len(self.view()["folders"]), 5)

    def test_exact_mode_replaces_local_selection_not_other_provider_partition(self):
        first, second = self.folder("source/first"), self.folder("source/second")
        root, _ = self.scout()
        manager.refresh_provider(self.workspace, "scout", [root])
        state = self.state("scout")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(first))
        self.command("scan", "--mode", "exact", "--workspace", str(self.workspace), "--root", str(second))
        self.assertEqual([item["path"] for item in manager.load_registry(self.workspace)["workspaces"]], [str(second)])
        self.assertEqual(self.state("scout"), state)

    def test_refresh_catalog_is_not_registration_or_automatic_editor_selection(self):
        source = self.folder("source/non-repo")
        root, metadata = self.copilot(cwd=source)
        before = snapshot(root)
        with metadata_guard([root, source], [metadata]):
            result = manager.refresh_provider(self.workspace, "copilot", [root])
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["candidates"], 1)
        self.assertEqual(self.state("copilot")["selected"], [])
        self.assertEqual(manager.load_registry(self.workspace)["workspaces"], [])
        self.assertEqual(len(self.view()["folders"]), 1)
        self.assertEqual(snapshot(root), before)
        key = self.state("copilot")["catalog"][0]["pointer_id"]
        with metadata_guard([root, source], []):
            manager.provider_action(self.workspace, "copilot", "select", key)
        self.assertEqual(self.view()["folders"][1]["path"], str(source))

    def test_provider_scoped_merge_preserves_other_partitions_and_local_routes(self):
        local = self.folder("source/exact")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(local))
        copilot, _ = self.copilot()
        claude, _ = self.claude()
        scout, _ = self.scout()
        for name, root in (("copilot", copilot), ("claude", claude), ("scout", scout)):
            manager.refresh_provider(self.workspace, name, [root])
        before = manager.load_registry(self.workspace)
        self.copilot(2)
        manager.refresh_provider(self.workspace, "copilot", [copilot])
        after = manager.load_registry(self.workspace)
        self.assertEqual(after["providers"]["claude"], before["providers"]["claude"])
        self.assertEqual(after["providers"]["scout"], before["providers"]["scout"])
        self.assertEqual(after["workspaces"], before["workspaces"])
        self.assertEqual(len(after["providers"]["copilot"]["catalog"]), 2)

    def test_batched_refresh_commits_only_complete_scan_and_keeps_last_good_selected(self):
        source = self.folder("source/non-repo")
        root, _ = self.copilot(cwd=source)
        manager.refresh_provider(self.workspace, "copilot", [root])
        first = self.state("copilot")
        key = first["catalog"][0]["pointer_id"]
        manager.provider_action(self.workspace, "copilot", "select", key)
        self.copilot(2, source)
        self.copilot(3, source)
        result = manager.refresh_provider(self.workspace, "copilot", [root], Limits(batch_size=1))
        partial = self.state("copilot")
        self.assertEqual(result["status"], "refreshing")
        self.assertEqual(partial["catalog"], first["catalog"])
        self.assertEqual(partial["last_success_utc"], first["last_success_utc"])
        self.assertEqual(len(self.view()["folders"]), 2)
        self.assertEqual(len(partial["pending"]["catalog"]), 1)
        for _ in range(2):
            manager.refresh_provider(self.workspace, "copilot", limits=Limits(batch_size=1))
        complete = self.state("copilot")
        self.assertEqual(complete["status"], "fresh")
        self.assertIsNone(complete["pending"])
        self.assertEqual(len(complete["catalog"]), 3)
        self.assertEqual(complete["selected"], [key])

    def test_bad_later_batch_preserves_whole_last_good_catalog(self):
        root, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [root])
        old = self.state("copilot")
        self.copilot(2)
        _, bad = self.copilot(3)
        bad.write_text("id: invalid\n")
        manager.refresh_provider(self.workspace, "copilot", [root], Limits(batch_size=2))
        result = manager.refresh_provider(self.workspace, "copilot", limits=Limits(batch_size=2))
        state = self.state("copilot")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(state["catalog"], old["catalog"])
        self.assertEqual(state["last_success_utc"], old["last_success_utc"])
        self.assertIsNone(state["pending"])

    def test_unreadable_busy_size_time_and_schema_errors_mark_stale_preserve_all_metadata(self):
        root, path = self.claude()
        manager.refresh_provider(self.workspace, "claude", [root])
        old = self.state("claude")
        for code in ("metadata-unreadable", "native-busy", "file-size-bound", "count-bound", "time-bound", "schema-mismatch"):
            with self.subTest(code=code):
                with mock.patch.object(native, "scan_provider", side_effect=RoutingError(code)):
                    result = manager.refresh_provider(self.workspace, "claude", [root])
                state = self.state("claude")
                self.assertEqual(result["status"], "stale")
                self.assertEqual(state["error"], code)
                self.assertEqual(state["catalog"], old["catalog"])
                self.assertEqual(state["last_success_utc"], old["last_success_utc"])
        path.write_text("not-json")
        result = manager.refresh_provider(self.workspace, "claude")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(self.state("claude")["catalog"], old["catalog"])

    def test_native_missing_profile_retains_last_good_and_cli_failure_status(self):
        root, _ = self.scout()
        manager.refresh_provider(self.workspace, "scout", [root])
        old = self.state("scout")
        root.rename(root.with_name("unavailable"))
        result, output = self.command("provider", "refresh", "--workspace", str(self.workspace), "--provider", "scout")
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output)["status"], "stale")
        self.assertEqual(self.state("scout")["catalog"], old["catalog"])

    def test_profile_set_change_is_atomic_and_native_identity_is_not_collapsed(self):
        root, _ = self.copilot()
        other, _ = self.copilot(profile="native/second-profile")
        manager.refresh_provider(self.workspace, "copilot", [root, other])
        state = self.state("copilot")
        self.assertEqual(len(state["catalog"]), 2)
        self.assertNotEqual(state["catalog"][0]["pointer_id"], state["catalog"][1]["pointer_id"])
        manager.refresh_provider(self.workspace, "copilot", [other, self.root / "missing"])
        self.assertEqual(self.state("copilot")["catalog"], state["catalog"])
        self.assertEqual(self.state("copilot")["profileRoots"], state["profileRoots"])
        manager.refresh_provider(self.workspace, "copilot", [other])
        self.assertEqual(len(self.state("copilot")["catalog"]), 1)
        self.assertEqual(self.state("copilot")["profileRoots"], [str(other)])

    def test_clear_cache_rediscovery_forget_suppression_explicit_readd(self):
        source = self.folder("source/work")
        root, metadata = self.copilot(cwd=source)
        manager.refresh_provider(self.workspace, "copilot", [root])
        key = self.state("copilot")["catalog"][0]["pointer_id"]
        before = snapshot(root)
        with metadata_guard([root, source], [metadata]):
            manager.provider_action(self.workspace, "copilot", "select", key)
            manager.provider_action(self.workspace, "copilot", "clear-cache", key)
            self.assertEqual(self.state("copilot")["catalog"], [])
            self.assertEqual(len(self.view()["folders"]), 1)
            manager.refresh_provider(self.workspace, "copilot")
            self.assertEqual(len(self.state("copilot")["catalog"]), 1)
            self.assertEqual(self.state("copilot")["selected"], [])
            manager.provider_action(self.workspace, "copilot", "select", key)
            manager.provider_action(self.workspace, "copilot", "forget", key)
            self.assertEqual(self.state("copilot")["forgotten"], [key])
            manager.refresh_provider(self.workspace, "copilot")
            self.assertEqual(self.state("copilot")["catalog"], [])
            manager.provider_action(self.workspace, "copilot", "clear-cache")
            manager.refresh_provider(self.workspace, "copilot")
            self.assertEqual(self.state("copilot")["catalog"], [])
            manager.provider_action(self.workspace, "copilot", "re-add", key)
            self.assertEqual(self.state("copilot")["forgotten"], [])
            self.assertEqual(len(self.view()["folders"]), 1)
            manager.refresh_provider(self.workspace, "copilot")
            self.assertEqual(self.state("copilot")["selected"], [key])
            self.assertEqual(len(self.view()["folders"]), 2)
        self.assertEqual(snapshot(root), before)

    def test_forget_drops_incomplete_checkpoint_and_cannot_be_undone_by_refresh(self):
        root, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [root])
        key = self.state("copilot")["catalog"][0]["pointer_id"]
        self.copilot(2)
        manager.refresh_provider(self.workspace, "copilot", limits=Limits(batch_size=1))
        manager.provider_action(self.workspace, "copilot", "forget", key)
        self.assertIsNone(self.state("copilot")["pending"])
        manager.refresh_provider(self.workspace, "copilot")
        self.assertNotIn(key, [item["pointer_id"] for item in self.state("copilot")["catalog"]])

    def test_local_clear_forget_readd_preserves_source_identity_and_no_content_access(self):
        source = self.folder("source/project")
        identity = {
            "schema": "rapp/1", "kind": "workspace", "rappid": "rappid:@example/project:" + "b" * 64,
            "mode": "solo", "world_id": "synthetic-project", "tags": ["example"],
            "instructions": "FORBIDDEN-CONTENT",
        }
        write_json(source / "rappid.json", identity)
        (source / "source.py").write_text("FORBIDDEN-SOURCE")
        before = snapshot(source)
        with metadata_guard([source], [source / "rappid.json"]):
            estate = ("estate", "--workspace", str(self.workspace), "--root", str(source))
            self.command(*estate)
            self.command("clear", "--workspace", str(self.workspace), "--path", str(source))
            self.assertEqual(len(self.view()["folders"]), 1)
            self.command(*estate)
            self.assertEqual(len(self.view()["folders"]), 2)
            self.command("forget", "--workspace", str(self.workspace), "--path", str(source))
            self.command(*estate)
            self.assertEqual(len(self.view()["folders"]), 1)
            self.command("re-add", "--workspace", str(self.workspace), "--path", str(source))
        entry = manager.load_registry(self.workspace)["workspaces"][0]
        self.assertEqual(entry["rappid"], identity["rappid"])
        self.assertEqual(entry["kind"], "rapp-workspace")
        self.assertEqual(snapshot(source), before)
        self.assertNotIn("FORBIDDEN", (self.workspace / "registry.json").read_text())

    def test_scout_nonlocal_and_protected_fallback_visible_but_not_editor_roots(self):
        fallback = self.folder("native/scout/workspace")
        local = self.folder("source/scout-work")
        root, metadata = self.scout([
            {"id": "local", "providerId": "local", "rootId": str(local)},
            {"id": "opaque", "providerId": "odsp", "rootId": str(local)},
            {"id": "fallback", "providerId": "local", "rootId": str(fallback)},
        ])
        (fallback / "session.jsonl").write_text("FORBIDDEN")
        manager.refresh_provider(self.workspace, "scout", [root])
        before = snapshot(root)
        with metadata_guard([root, local], []), mock.patch(
            "subprocess.run", side_effect=AssertionError("no native delete/disconnect/close")
        ):
            for item in self.state("scout")["catalog"]:
                manager.provider_action(self.workspace, "scout", "select", item["pointer_id"])
            self.assertEqual(len(self.view()["folders"]), 2)
            home = (self.workspace / "HOME.md").read_text()
            self.assertIn("opaque (odsp)", home)
            self.assertIn("nonlocal:", home)
            manager.provider_action(self.workspace, "scout", "clear")
            self.assertEqual(len(self.view()["folders"]), 1)
        self.assertEqual(snapshot(root), before)

    def test_hermes_wal_stale_last_good_and_source_checkout_is_separate(self):
        checkout = self.folder("sources/hermes-checkout")
        root = self.folder("native/hermes")
        db = sqlite3.connect(root / "state.db")
        db.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT, title TEXT)")
        db.execute("INSERT INTO sessions VALUES ('s1', NULL, 'FORBIDDEN')")
        db.commit()
        db.close()
        manager.refresh_provider(self.workspace, "hermes", [root])
        state = self.state("hermes")
        self.assertEqual(state["catalog"][0]["metadata"]["cwd"], None)
        self.command("estate", "--workspace", str(self.workspace), "--root", str(checkout))
        db = sqlite3.connect(root / "state.db")
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO sessions VALUES ('s2', NULL, 'FORBIDDEN')")
            db.commit()
            before = snapshot(root)
            result = manager.refresh_provider(self.workspace, "hermes")
            self.assertEqual(result["error"], "native-wal-active")
            self.assertEqual(self.state("hermes")["catalog"], state["catalog"])
            self.assertEqual(snapshot(root), before)
            self.assertEqual(self.view()["folders"][1]["path"], str(checkout))
        finally:
            db.close()

    def test_grok_app_only_refuses_selection_exact_explicit_project_is_independent(self):
        app = self.folder("Grokbot.app")
        (app / "opaque-state").write_text("FORBIDDEN")
        manager.refresh_provider(self.workspace, "grokbot", [app])
        self.assertEqual(self.state("grokbot")["catalog"], [])
        self.assertIn("workspace-mapping-unavailable", (self.workspace / "HOME.md").read_text())
        with self.assertRaises(RoutingError):
            manager.provider_action(self.workspace, "grokbot", "select", "grokbot:" + "a" * 64)
        with self.assertRaises(RoutingError):
            self.command("estate", "--workspace", str(self.workspace), "--root", str(app))
        selected = self.folder("source/owner-selected-bot-project")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(selected))
        self.assertEqual(len(self.view()["folders"]), 2)
        self.assertEqual(self.state("grokbot")["catalog"], [])

    def test_editor_determinism_jsonc_settings_extensions_and_atomic_replace(self):
        source = self.folder("source/project")
        view_path = self.workspace / "estate.code-workspace"
        view_path.write_text("""{
          // Owner settings and extensions are not routing authority.
          "settings": {"files.autoSave": "off", "custom": "https://example.test/a,}",},
          "extensions": {"recommendations": ["example.extension"],},
          "launch": {"version": "0.2.0", "configurations": [],},
          "folders": [{"path": "/synthetic/obsolete"}],
        }""")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(source))
        first = view_path.read_bytes()
        view = json.loads(first)
        self.assertEqual(view["settings"], {"files.autoSave": "off", "custom": "https://example.test/a,}"})
        self.assertEqual(view["extensions"], {"recommendations": ["example.extension"]})
        self.assertEqual(view["launch"]["version"], "0.2.0")
        original_replace = os.replace
        commits = []

        def replacing(src, dst, **kwargs):
            if dst == "estate.code-workspace":
                self.assertEqual(view_path.read_bytes(), first)
                self.assertTrue(str(src).endswith(".pending"))
                self.assertEqual(kwargs["src_dir_fd"], kwargs["dst_dir_fd"])
                commits.append(dst)
            return original_replace(src, dst, **kwargs)

        with mock.patch.object(routing_io.os, "replace", side_effect=replacing):
            self.command("editor-view", "--workspace", str(self.workspace))
        self.assertEqual(commits, ["estate.code-workspace"])
        self.assertEqual(view_path.read_bytes(), first)
        self.assertEqual(list(self.workspace.glob("*.pending")), [])
        self.assertEqual(list(self.workspace.glob(".*.pending")), [])

    def test_editor_atomic_failure_keeps_previous_file_and_cleans_staging(self):
        path = self.workspace / "estate.code-workspace"
        before = path.read_bytes()
        with mock.patch.object(routing_io.os, "replace", side_effect=OSError("synthetic rename failure")):
            with self.assertRaises((OSError, RoutingError)):
                routing_io.atomic_json(path, {"folders": ["not-committed"]})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.workspace.glob(".*.pending")), [])

    def test_custom_editor_filename_confined_to_manager_and_preserves_other_settings(self):
        custom = self.workspace / "selected.code-workspace"
        custom.write_text('{"settings":{"owner.setting":true}}')
        self.command("editor-view", "--workspace", str(self.workspace), "--output", str(custom))
        self.assertEqual(manager.load_registry(self.workspace)["editor_view"], custom.name)
        self.assertTrue(json.loads(custom.read_text())["settings"]["owner.setting"])
        for output in (
            "../outside.code-workspace", str(self.root / "outside.code-workspace"),
            "registry.json", ".hidden.code-workspace", "nested/view.code-workspace",
        ):
            with self.subTest(output=output), self.assertRaises(RoutingError):
                self.command("editor-view", "--workspace", str(self.workspace), "--output", output)

    def test_corrupt_or_symlink_projection_fails_closed_before_registry_mutation(self):
        source = self.folder("source/project")
        view = self.workspace / "estate.code-workspace"
        registry_before = (self.workspace / "registry.json").read_bytes()
        view.write_text("not-jsonc")
        with self.assertRaises(RoutingError):
            self.command("estate", "--workspace", str(self.workspace), "--root", str(source))
        self.assertEqual((self.workspace / "registry.json").read_bytes(), registry_before)
        view.unlink()
        forbidden = source / "secret"
        forbidden.write_text("FORBIDDEN")
        view.symlink_to(forbidden)
        with metadata_guard([source], [source / "rappid.json"]), self.assertRaises(RoutingError):
            self.command("estate", "--workspace", str(self.workspace), "--root", str(source))
        self.assertEqual(forbidden.read_text(), "FORBIDDEN")
        self.assertEqual((self.workspace / "registry.json").read_bytes(), registry_before)

    def test_symlink_selected_directory_drops_projection_without_reading_destination(self):
        source = self.folder("source/project")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(source))
        source.rmdir()
        forbidden = self.folder("forbidden")
        (forbidden / "secret").write_text("FORBIDDEN")
        source.symlink_to(forbidden, target_is_directory=True)
        with metadata_guard([forbidden], []):
            self.command("editor-view", "--workspace", str(self.workspace))
        self.assertEqual(len(self.view()["folders"]), 1)
        self.assertEqual(len(manager.load_registry(self.workspace)["workspaces"]), 1)
        with self.assertRaises(RoutingError):
            self.command("open", "--workspace", str(self.workspace), "--name", "project", "--print-path")

    def test_manager_registry_identity_world_closed_union_and_legacy_read(self):
        path = self.workspace / "registry.json"
        original = json.loads(path.read_text())
        source = self.folder("source/project")
        legacy = copy.deepcopy(original)
        legacy.pop("providers")
        legacy.pop("forgotten")
        legacy.pop("editor_view")
        legacy.pop("editor_views")
        legacy["workspaces"] = [{
            "name": source.name, "path": str(source), "kind": "git",
            "mode": None, "rappid": None, "world_id": None, "tags": [],
        }]
        write_json(path, legacy)
        self.assertEqual(manager.load_registry(self.workspace)["workspaces"][0]["pointer_type"], "local-directory")
        for data in (
            {**original, "schema": "unknown/2"},
            {**original, "world_id": "other"},
            {**original, "manager_rappid": "other"},
            {**original, "chats": ["FORBIDDEN"]},
            {**original, "providers": {"other": manager.empty_provider()}},
        ):
            write_json(path, data)
            with self.subTest(data=data), self.assertRaises(RoutingError):
                manager.load_registry(self.workspace)

    def test_duplicate_names_refused_and_pointer_open_never_reads_source(self):
        one, two = self.folder("source/one/project"), self.folder("source/two/project")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(one), "--root", str(two))
        with self.assertRaisesRegex(RoutingError, "ambiguous"):
            self.command("open", "--workspace", str(self.workspace), "--name", "project", "--print-path")
        self.command("clear", "--workspace", str(self.workspace), "--path", str(two))
        with metadata_guard([one, two], []):
            _, result = self.command("open", "--workspace", str(self.workspace), "--name", "project", "--print-path")
        self.assertEqual(result.strip(), str(one))

    def test_no_home_recursive_scan_native_overlap_or_manager_containment(self):
        for root in (Path.home(), self.folder(".copilot"), self.root):
            if root == self.root:
                with self.assertRaises(RoutingError):
                    self.command("estate", "--workspace", str(self.workspace), "--root", str(root))
                with self.assertRaises(RoutingError):
                    self.command("estate", "--workspace", str(self.workspace), "--root", str(root.parent))
            else:
                with self.assertRaises(RoutingError):
                    self.command("scan", "--workspace", str(self.workspace), "--root", str(root))
        root, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [root])
        with self.assertRaises(RoutingError):
            self.command("estate", "--workspace", str(self.workspace), "--root", str(root))
        with self.assertRaises(RoutingError):
            manager.refresh_provider(self.workspace, "copilot", [self.workspace])
        with self.assertRaises(RoutingError):
            self.command("estate", "--workspace", str(self.workspace), "--root", str(self.workspace / "projects"))

    def test_inspect_and_list_no_registry_writes_no_native_lifecycle_apis(self):
        root, path = self.copilot()
        before = snapshot(self.workspace)
        with metadata_guard([root], [path]):
            result, output = self.command("provider", "inspect", "--provider", "copilot", "--profile-root", str(root))
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(output)["complete"])
        self.assertEqual(snapshot(self.workspace), before)
        manager.refresh_provider(self.workspace, "copilot", [root])
        before = snapshot(self.workspace)
        with metadata_guard([root], []):
            _, output = self.command("provider", "list", "--provider", "copilot", "--workspace", str(self.workspace))
        self.assertEqual(len(json.loads(output)["catalog"]), 1)
        self.assertEqual(snapshot(self.workspace), before)
        for verb in ("delete", "disconnect", "close"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                manager.parser().parse_args(["provider", verb, "--provider", "scout"])

    def test_selected_multi_path_claude_and_unresolved_missing_index_coexist(self):
        one, two = self.folder("source/a-b"), self.folder("source/a/b")
        root, index = self.claude(cwd=one)
        write_json(index, {"version": 1, "originalPath": str(one), "entries": [{"projectPath": str(two)}]})
        missing = self.folder("native/claude/projects/-source-a-b")
        (missing / "transcript.jsonl").write_text("FORBIDDEN")
        manager.refresh_provider(self.workspace, "claude", [root])
        for item in self.state("claude")["catalog"]:
            manager.provider_action(self.workspace, "claude", "select", item["pointer_id"])
        self.assertEqual({item["path"] for item in self.view()["folders"]}, {str(self.workspace), str(one), str(two)})
        self.assertIn("missing-index", (self.workspace / "HOME.md").read_text())

    def test_staging_catalog_size_bound_preserves_last_good(self):
        root, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [root])
        old = self.state("copilot")
        with mock.patch.object(native, "MAX_CATALOG_BYTES", 1):
            result = manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["error"], "catalog-size-bound")
        self.assertEqual(self.state("copilot")["catalog"], old["catalog"])

    def test_manager_lock_refuses_concurrent_mutation_and_symlinked_lock(self):
        root, _ = self.copilot()
        with routing_io.manager_lock(self.workspace):
            before = (self.workspace / "registry.json").read_bytes()
            with self.assertRaises(RoutingError):
                manager.refresh_provider(self.workspace, "copilot", [root])
            self.assertEqual((self.workspace / "registry.json").read_bytes(), before)
        lock = self.workspace / ".routing.lock"
        lock.unlink()
        forbidden = self.root / "native-lock-target"
        forbidden.write_text("FORBIDDEN")
        lock.symlink_to(forbidden)
        with metadata_guard([forbidden], []), self.assertRaises(RoutingError):
            manager.refresh_provider(self.workspace, "copilot", [root])
        self.assertEqual(forbidden.read_text(), "FORBIDDEN")

    def test_bounds_failure_never_replaces_local_scan_partition(self):
        source = self.folder("source/current")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(source))
        before = (self.workspace / "registry.json").read_bytes()
        for number in range(3):
            self.folder(f"discovery/repo-{number}/.git")
        with self.assertRaisesRegex(RoutingError, "count-bound"):
            self.command(
                "scan", "--workspace", str(self.workspace), "--root", str(self.root / "discovery"),
                "--max-entries", "1",
            )
        self.assertEqual((self.workspace / "registry.json").read_bytes(), before)

    def test_known_native_paths_cannot_be_manager_init_or_save_destinations(self):
        original = manager.load_registry(self.workspace)
        identity = manager.manager_identity(self.workspace)
        for relative in (".copilot/fake-manager", ".scout/workspace", ".grok/skills"):
            path = self.root / relative
            with self.subTest(path=relative), self.assertRaises(RoutingError):
                self.command("init", "--workspace", str(path), "--owner", "example")
            self.assertFalse(path.exists())
            with self.assertRaises(RoutingError):
                manager.save_registry(path, identity, original)

    def test_clear_updates_all_previously_generated_views_and_preserves_each_settings(self):
        source = self.folder("source/shared")
        self.command("estate", "--workspace", str(self.workspace), "--root", str(source))
        second = self.workspace / "second.code-workspace"
        second.write_text('{"settings":{"example.ownedSetting":"keep"}}')
        self.command("editor-view", "--workspace", str(self.workspace), "--output", second.name)
        self.assertEqual(len(json.loads((self.workspace / "estate.code-workspace").read_text())["folders"]), 2)
        self.command("forget", "--workspace", str(self.workspace), "--path", str(source))
        for path in (self.workspace / "estate.code-workspace", second):
            self.assertEqual(len(json.loads(path.read_text())["folders"]), 1)
        self.assertEqual(json.loads(second.read_text())["settings"]["example.ownedSetting"], "keep")

    def test_shared_local_reference_remains_when_another_selected_provider_still_owns_pointer(self):
        source = self.folder("source/shared")
        copilot, _ = self.copilot(cwd=source)
        claude, _ = self.claude(cwd=source)
        for provider, root in (("copilot", copilot), ("claude", claude)):
            manager.refresh_provider(self.workspace, provider, [root])
            manager.provider_action(self.workspace, provider, "select", self.state(provider)["catalog"][0]["pointer_id"])
        self.assertEqual(len(self.view()["folders"]), 2)
        claude_state = self.state("claude")
        manager.provider_action(self.workspace, "copilot", "forget")
        self.assertEqual(len(self.view()["folders"]), 2)
        self.assertEqual(self.state("claude"), claude_state)

    def test_recursive_discovery_skips_registered_native_profile_subtree(self):
        profile, metadata = self.copilot()
        (metadata.parent / ".git").mkdir()
        (profile / "private/child/.git").mkdir(parents=True)
        manager.refresh_provider(self.workspace, "copilot", [profile])
        with mock.patch.object(manager, "read_workspace_pointer", side_effect=AssertionError("native pointer must not become Git root")):
            self.command("scan", "--workspace", str(self.workspace), "--root", str(profile.parent))
        self.assertEqual(manager.load_registry(self.workspace)["workspaces"], [])

    def test_public_synthetic_metadata_examples_match_actual_adapter_shapes(self):
        examples = Path(__file__).parents[1] / "examples"
        manager.validate_registry(json.loads((examples / "registry.example.json").read_text()))
        profile, yaml = self.copilot()
        yaml.write_bytes((examples / "native/copilot/workspace.yaml").read_bytes())
        claude, index = self.claude()
        index.write_bytes((examples / "native/claude/sessions-index.json").read_bytes())
        scout, manifest = self.scout()
        manifest.write_bytes((examples / "native/scout/workspaces.json").read_bytes())
        hermes = self.folder("native/hermes")
        db = sqlite3.connect(hermes / "state.db")
        db.executescript((examples / "native/hermes/metadata-schema.sql").read_text())
        db.close()
        app = self.folder("Grokbot.app")
        expected = {"copilot": 1, "claude": 1, "hermes": 4, "scout": 2, "grokbot": 0}
        for provider, root in (("copilot", profile), ("claude", claude), ("hermes", hermes), ("scout", scout), ("grokbot", app)):
            result = native.scan_provider(provider, [root])
            self.assertTrue(result["complete"])
            self.assertEqual(len(result["catalog"]), expected[provider])
        example = json.loads((examples / "native/grokbot/observation.json").read_text())
        example["profileRoot"] = str(app)
        example["observation_id"] = native.grokbot_observation_id(app)
        example["observation_version"] = 2
        example["profileIdentity"] = routing_io.directory_identity(app)
        self.assertEqual(result["observations"], [example])

    def test_registry_size_bound_keeps_provider_last_good_with_stale_error(self):
        root, _ = self.copilot()
        manager.refresh_provider(self.workspace, "copilot", [root])
        before = self.state("copilot")
        maximum = (self.workspace / "registry.json").stat().st_size + 1000
        for number in range(2, 15):
            self.copilot(number)
        with mock.patch.object(manager, "MAX_REGISTRY_BYTES", maximum):
            result = manager.refresh_provider(self.workspace, "copilot")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["error"], "registry-size-bound")
        self.assertEqual(self.state("copilot")["catalog"], before["catalog"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can bypass file read permissions")
    def test_real_unreadable_manifest_preserves_last_good_without_native_repair(self):
        root, metadata = self.scout()
        manager.refresh_provider(self.workspace, "scout", [root])
        before = self.state("scout")
        original = metadata.read_bytes()
        metadata.chmod(0)
        try:
            result = manager.refresh_provider(self.workspace, "scout")
            self.assertEqual(result["status"], "stale")
            self.assertEqual(result["error"], "metadata-unreadable")
            self.assertEqual(self.state("scout")["catalog"], before["catalog"])
            self.assertEqual(metadata.stat().st_mode & 0o777, 0)
        finally:
            metadata.chmod(0o600)
        self.assertEqual(metadata.read_bytes(), original)

    def test_grok_observation_clear_forget_readd_never_becomes_a_workspace_mapping(self):
        app = self.folder("Grokbot.app")
        (app / "settings.json").write_text("FORBIDDEN")
        before = snapshot(app)
        with metadata_guard([app], []):
            manager.refresh_provider(self.workspace, "grokbot", [app])
            key = self.state("grokbot")["observations"][0]["observation_id"]
            with self.assertRaises(RoutingError):
                manager.provider_action(self.workspace, "grokbot", "select", key)
            manager.provider_action(self.workspace, "grokbot", "clear-cache", key)
            self.assertEqual(self.state("grokbot")["observations"], [])
            manager.refresh_provider(self.workspace, "grokbot")
            self.assertEqual(len(self.state("grokbot")["observations"]), 1)
            manager.provider_action(self.workspace, "grokbot", "forget", key)
            manager.refresh_provider(self.workspace, "grokbot")
            self.assertEqual(self.state("grokbot")["observations"], [])
            self.assertEqual(self.state("grokbot")["forgotten"], [key])
            manager.provider_action(self.workspace, "grokbot", "re-add", key)
            manager.refresh_provider(self.workspace, "grokbot")
            self.assertEqual(len(self.state("grokbot")["observations"]), 1)
            self.assertEqual(self.state("grokbot")["catalog"], [])
            self.assertEqual(self.state("grokbot")["selected"], [])
            self.assertEqual(len(self.view()["folders"]), 1)
        self.assertEqual(snapshot(app), before)


if __name__ == "__main__":
    unittest.main()
