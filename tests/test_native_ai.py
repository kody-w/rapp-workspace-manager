import copy
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
from routing_io import Budget, Limits, RoutingError
from support import fixture_directory, metadata_guard, snapshot, write_json


def session_id(number=1):
    return f"00000000-0000-4000-8000-{number:012d}"


class NativeAdapterTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_directory()
        self.root = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)

    def folder(self, relative):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copilot(self, number=1, cwd=None, profile="copilot-profile", extra="", metadata=True):
        root = self.folder(profile)
        directory = self.folder(f"{profile}/session-state/{session_id(number)}")
        path = directory / "workspace.yaml"
        if metadata:
            path.write_text(
                f"id: {session_id(number)}\ncwd: {json.dumps(str(cwd)) if cwd else 'null'}\n"
                "branch: ''\nhost_type: cli\n" + extra,
                encoding="utf-8",
            )
        return root, path

    def claude(self, key="native-key", data=None, profile="claude-profile"):
        root = self.folder(profile)
        bucket = self.folder(f"{profile}/projects/{key}")
        path = bucket / "sessions-index.json"
        if data is not None:
            write_json(path, data)
        return root, path

    def scout(self, entries, version=3):
        root = self.folder("scout-profile")
        path = write_json(root / "m-sessions/workspaces.json", {"version": version, "workspaces": entries})
        return root, path

    def hermes(self, schema=None):
        root = self.folder("hermes-profile")
        connection = sqlite3.connect(root / "state.db")
        connection.executescript(schema or """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, project_id TEXT, folder_id TEXT, cwd TEXT,
                created_at REAL, updated_at REAL,
                title TEXT, preview TEXT, system_prompt TEXT, config_blob BLOB
            );
            CREATE TABLE projects (id TEXT PRIMARY KEY, path TEXT, title TEXT);
            CREATE TABLE folders (id TEXT PRIMARY KEY, project_id TEXT, path TEXT, name TEXT);
            CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, content TEXT);
        """)
        return root, connection

    def test_copilot_nonrepo_nested_worktree_and_identity_per_profile(self):
        nonrepo = self.folder("source/notes")
        nested = self.folder("source/repo/deep/nested")
        worktree = self.folder("source/worktree")
        (worktree / ".git").write_text("gitdir: forbidden-source-content")
        profiles, allowed = [], []
        for number, cwd in enumerate((nonrepo, nested, worktree), 1):
            root, path = self.copilot(number, cwd, extra="repository: example/project\n")
            profiles.append(root)
            allowed.append(path)
            (path.parent / "events.jsonl").write_text("FORBIDDEN-CHAT")
            (path.parent / "session.db").write_text("FORBIDDEN-DB")
            (path.parent / "files").mkdir()
            (path.parent / "files" / "secret.txt").write_text("FORBIDDEN-ATTACHMENT")
        second, path = self.copilot(1, nonrepo, profile="second-profile")
        profiles.append(second)
        allowed.append(path)
        before = snapshot(self.root)
        with metadata_guard([self.root / "source", *profiles], allowed) as opened:
            result = native.scan_provider("copilot", profiles)
            self.assertTrue(result["complete"])
            self.assertEqual(len(result["catalog"]), 4)
            resolved = {path for item in result["catalog"] for path in native.local_paths(item)}
        self.assertEqual(resolved, {str(nonrepo), str(nested), str(worktree)})
        self.assertEqual(len(set(item["pointer_id"] for item in result["catalog"])), 4)
        self.assertEqual(set(opened), set(map(str, allowed)))
        self.assertEqual(snapshot(self.root), before)
        self.assertNotIn("FORBIDDEN", json.dumps(result))

    def test_copilot_allowlist_scalars_no_summary_or_complex_yaml_interpretation(self):
        source = self.folder("source/example")
        root, path = self.copilot(1, source, extra=(
            "client_name: \"editor #1\" # comment\nupdated_at: 2026-01-01T00:00:00Z\n"
            "summary: |\n  FORBIDDEN-SUMMARY\n  cwd: /invented\n"
            "todos: FORBIDDEN-TODO\n"
        ))
        result = native.scan_provider("copilot", [root])
        item = result["catalog"][0]
        self.assertEqual(item["metadata"]["cwd"], str(source))
        self.assertEqual(item["metadata"]["client_name"], "editor #1")
        self.assertNotIn("FORBIDDEN", json.dumps(result))
        for bad in (
            "cwd: !!python/object:forbidden\n", "cwd: [one, two]\n",
            "cwd: |\n  /somewhere\n", "id: wrong-id\n", "id: one\nid: two\n",
        ):
            with self.subTest(bad=bad):
                path.write_text(bad)
                with self.assertRaises(RoutingError):
                    native.scan_provider("copilot", [root])
        path.write_text(f"id: {session_id()}\ncwd: null # not a path\nbranch: # unknown\n")
        item = native.scan_provider("copilot", [root])["catalog"][0]
        self.assertIsNone(item["metadata"]["cwd"])
        self.assertIsNone(item["metadata"]["branch"])

    def test_copilot_missing_cwd_missing_metadata_and_uuid_filter(self):
        root, _ = self.copilot(1)
        self.copilot(2, metadata=False)
        outside = self.folder("copilot-profile/session-state/not-a-uuid")
        (outside / "workspace.yaml").write_text("secret: FORBIDDEN")
        result = native.scan_provider("copilot", [root])
        self.assertEqual(len(result["catalog"]), 2)
        self.assertEqual({item["availability"] for item in result["catalog"]}, {"metadata", "missing-metadata"})
        self.assertTrue(all(native.local_paths(item) == [] for item in result["catalog"]))

    def test_copilot_many_sessions_batched_then_incrementally_cached(self):
        root, _ = self.copilot()
        for number in range(2, 258):
            self.copilot(number)
        limits = Limits(batch_size=37, max_entries=300)
        pending, calls, final = None, 0, None
        while final is None:
            with mock.patch.object(native, "read_bytes", wraps=native.read_bytes) as reads:
                result = native.scan_provider("copilot", [root], pending=pending, limits=limits)
                self.assertLessEqual(reads.call_count, 37)
            calls += 1
            if result["complete"]:
                final = result
            else:
                self.assertEqual(result["catalog"], [])
                pending = result["pending"]
        self.assertEqual(calls, 7)
        self.assertEqual(len(final["catalog"]), 257)
        with mock.patch.object(native, "read_bytes", side_effect=AssertionError("unchanged metadata re-read")):
            cached = native.scan_provider(
                "copilot", [root], previous=final["catalog"], limits=Limits(batch_size=300)
            )
        self.assertEqual(cached["reused"], 257)
        self.assertEqual(cached["catalog"], final["catalog"])

    def test_copilot_changed_inventory_and_hostile_checkpoint_refused(self):
        root, _ = self.copilot()
        self.copilot(2)
        result = native.scan_provider("copilot", [root], limits=Limits(batch_size=1))
        pending = result["pending"]
        bad = copy.deepcopy(pending)
        bad["inventories"][0]["names"][0] = "../events.jsonl"
        with self.assertRaises(RoutingError):
            native.scan_provider("copilot", [root], pending=bad)
        self.copilot(3)
        with self.assertRaisesRegex(RoutingError, "inventory-changed-retry"):
            native.scan_provider("copilot", [root], pending=pending)

    def test_copilot_99000_name_inventory_keeps_metadata_work_per_call_bounded(self):
        root, _ = self.copilot()
        names = [session_id(number) for number in range(99000)]
        source_stamp = routing_io.stamp((root / "session-state").stat())

        def item(profile, identity, previous, budget, profile_identity=None):
            return native.pointer(
                "copilot", profile, "copilot-session", identity, nativeSessionId=identity,
                profile_identity=profile_identity,
                metadata={}, sourceStamp=None, availability="missing-metadata",
            ), False

        with mock.patch.object(native, "child_directories", return_value=(names, source_stamp)):
            with mock.patch.object(native, "_copilot_item", side_effect=item) as read:
                result = native.scan_provider("copilot", [root], limits=Limits(batch_size=250))
                self.assertEqual(read.call_count, 250)
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["pending"]["inventories"][0]["names"]), 99000)
        self.assertEqual(len(result["pending"]["catalog"]), 250)
        self.assertEqual(result["catalog"], [])

    def test_copilot_changed_yaml_only_re_reads_changed_item(self):
        root, path = self.copilot()
        self.copilot(2)
        first = native.scan_provider("copilot", [root])
        path.write_text(f"id: {session_id()}\nbranch: new-branch\n")
        with mock.patch.object(native, "read_bytes", wraps=native.read_bytes) as reads:
            second = native.scan_provider("copilot", [root], previous=first["catalog"])
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(second["reused"], 1)

    def test_claude_multi_path_associations_preserve_native_key(self):
        original = self.folder("source/a-b")
        other = self.folder("source/a/b")
        third = self.folder("source/punctuation_! [x]")
        root, index = self.claude("-native-opaque-key", {
            "version": 1, "originalPath": str(original),
            "entries": [
                {"projectPath": str(other), "summary": "FORBIDDEN", "fullPath": "/never/transcript.jsonl"},
                {"originalPath": str(third), "projectPath": str(third), "firstPrompt": "FORBIDDEN"},
                {"projectPath": str(other)},
            ],
        })
        (index.parent / "transcript.jsonl").write_text("FORBIDDEN")
        before = snapshot(self.root)
        with metadata_guard([root, self.root / "source"], [index]):
            item = native.scan_provider("claude", [root])["catalog"][0]
            paths = native.local_paths(item)
        self.assertEqual(item["nativeKey"], "-native-opaque-key")
        self.assertEqual(item["nativeRoot"], str(root / "projects"))
        self.assertEqual(len(item["pathAssociations"]), 2)
        self.assertEqual(set(paths), {str(original), str(other), str(third)})
        self.assertNotIn("FORBIDDEN", json.dumps(item))
        self.assertEqual(snapshot(self.root), before)

    def test_claude_missing_index_no_hyphen_reverse_mapping(self):
        self.folder("source/a-b")
        self.folder("source/a/b")
        root, index = self.claude("-source-a-b")
        (index.parent / "session.jsonl").write_text("FORBIDDEN")
        with metadata_guard([root], []):
            item = native.scan_provider("claude", [root])["catalog"][0]
        self.assertEqual(item["availability"], "missing-index")
        self.assertIsNone(item["originalPath"])
        self.assertEqual(item["pathAssociations"], [])
        self.assertEqual(native.local_paths(item), [])

    def test_claude_unknown_malformed_schema_and_no_content_fallback(self):
        for data in (
            {"version": 2, "entries": []}, {"version": True, "entries": []},
            {"version": 1, "entries": {}}, {"version": 1, "entries": ["bad"]},
        ):
            root, _ = self.claude(data=data)
            with self.subTest(data=data), self.assertRaises(RoutingError):
                native.scan_provider("claude", [root])
        root, path = self.claude()
        path.write_text('{"version":1,"version":2,"entries":[]}')
        with self.assertRaisesRegex(RoutingError, "malformed"):
            native.scan_provider("claude", [root])

    def test_hermes_metadata_columns_preserve_projects_folders_sessions_missing_cwd(self):
        project = self.folder("source/project")
        folder_a = self.folder("source/folder-a")
        folder_b = self.folder("source/folder-b")
        root, connection = self.hermes()
        connection.execute("INSERT INTO projects VALUES ('p', ?, 'FORBIDDEN-TITLE')", (str(project),))
        for index, folder in enumerate((folder_a, folder_b), 1):
            connection.execute("INSERT INTO folders VALUES (?, 'p', ?, 'FORBIDDEN-NAME')", (f"f{index}", str(folder)))
        connection.execute(
            "INSERT INTO sessions VALUES ('s1', 'p', 'f1', NULL, 1, 2, 'FORBIDDEN', 'FORBIDDEN', 'FORBIDDEN', X'FEED')"
        )
        connection.execute(
            "INSERT INTO sessions VALUES ('s2', 'p', 'f2', ?, 1, 2, 'FORBIDDEN', 'FORBIDDEN', 'FORBIDDEN', X'FEED')",
            (str(folder_b),),
        )
        connection.execute("INSERT INTO messages VALUES (1, 's1', 'terminal-session cwd=/unverified FORBIDDEN')")
        connection.commit()
        connection.close()
        before = snapshot(self.root)
        real_connect, queries = sqlite3.connect, []

        def traced(database_uri, **kwargs):
            self.assertIn("mode=ro&immutable=1", database_uri)
            db = real_connect(database_uri, **kwargs)
            db.set_trace_callback(queries.append)
            return db

        with metadata_guard([root, self.root / "source"], [root / "state.db"]):
            with mock.patch.object(native.sqlite3, "connect", side_effect=traced):
                result = native.scan_provider("hermes", [root])
            sessions = [item for item in result["catalog"] if item["pointer_type"] == "hermes-session"]
            missing = next(item for item in sessions if item["nativeId"] == "s1")
            self.assertEqual(native.local_paths(missing), [])
            resolved = {path for item in result["catalog"] for path in native.local_paths(item)}
        self.assertEqual(len(result["catalog"]), 5)
        self.assertEqual(resolved, set(map(str, (project, folder_a, folder_b))))
        self.assertEqual(missing["metadata"]["project_id"], "p")
        self.assertEqual(snapshot(self.root), before)
        self.assertNotIn("FORBIDDEN", json.dumps(result))
        for query in queries:
            self.assertNotIn('FROM "messages"', query)
            self.assertNotIn('"title"', query)
            self.assertNotIn('"system_prompt"', query)
            self.assertNotIn('"config_blob"', query)

    def test_hermes_no_cwd_column_stays_unknown_and_project_folders_keep_table_identity(self):
        root, connection = self.hermes("""
            CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT);
            INSERT INTO sessions VALUES ('s', 'FORBIDDEN');
            CREATE TABLE project_folders (id INTEGER PRIMARY KEY, project_id INTEGER, path TEXT);
            INSERT INTO project_folders VALUES (1, 7, NULL);
        """)
        connection.close()
        result = native.scan_provider("hermes", [root])
        self.assertEqual(len(result["catalog"]), 2)
        self.assertEqual({item["nativeTable"] for item in result["catalog"]}, {"sessions", "project_folders"})
        self.assertTrue(all(native.local_paths(item) == [] for item in result["catalog"]))
        self.assertNotIn("FORBIDDEN", json.dumps(result))

    def test_hermes_active_wal_refuses_no_wal_or_shm_writes(self):
        root, connection = self.hermes()
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO sessions (id) VALUES ('wal-only')")
        connection.commit()
        before = snapshot(root)
        try:
            with metadata_guard([root], [root / "state.db"]), mock.patch.object(
                native.sqlite3, "connect", side_effect=AssertionError("must not ignore WAL")
            ):
                with self.assertRaisesRegex(RoutingError, "native-wal-active"):
                    native.scan_provider("hermes", [root])
            self.assertEqual(snapshot(root), before)
        finally:
            connection.close()
        self.assertEqual(len(native.scan_provider("hermes", [root])["catalog"]), 1)

    def test_hermes_busy_database_refused_without_waiting_or_writes(self):
        root, connection = self.hermes()
        connection.close()
        script = (
            "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); "
            "db.execute('BEGIN EXCLUSIVE'); print('locked',flush=True); "
            "sys.stdin.readline(); db.rollback(); db.close()"
        )
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(root / "state.db")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "locked")
            before = snapshot(root)
            with self.assertRaisesRegex(RoutingError, "native-busy"):
                native.scan_provider("hermes", [root])
            self.assertEqual(snapshot(root), before)
        finally:
            process.communicate("\n", timeout=10)

    def test_hermes_schema_version_missing_id_view_and_invalid_db_refused(self):
        for number, schema in enumerate((
            "CREATE TABLE sessions (id TEXT); PRAGMA user_version=99;",
            "CREATE TABLE sessions (session_id TEXT);",
            "CREATE TABLE private (id TEXT); CREATE VIEW sessions AS SELECT id FROM private;",
            "CREATE TABLE sessions (id BLOB);",
        )):
            with self.subTest(schema=schema):
                root = self.folder(f"hermes-{number}")
                db = sqlite3.connect(root / "state.db")
                db.executescript(schema)
                db.close()
                with self.assertRaises(RoutingError):
                    native.scan_provider("hermes", [root])
        root = self.folder("broken-hermes")
        (root / "state.db").write_bytes(b"not-a-database")
        with self.assertRaises(RoutingError):
            native.scan_provider("hermes", [root])

    def test_scout_native_local_and_opaque_odsp_even_if_root_looks_like_path(self):
        local = self.folder("source/local")
        deceptive = self.folder("source/opaque-but-existing")
        root, manifest = self.scout([
            {"id": "local-workspace", "providerId": "local", "rootId": str(local), "name": "FORBIDDEN"},
            {"id": "cloud-workspace", "providerId": "odsp", "rootId": str(deceptive)},
            {"id": "opaque", "providerId": "odsp", "rootId": "odsp:opaque-root-reference"},
        ])
        fallback = self.folder("scout-profile/workspace")
        write_json(manifest, {
            "version": 3,
            "workspaces": json.loads(manifest.read_text())["workspaces"] + [
                {"id": "fallback", "providerId": "local", "rootId": str(fallback)}
            ],
        })
        (root / "auth.json").write_text("FORBIDDEN")
        self.folder("scout-profile/browser")
        (root / "browser/state.json").write_text("FORBIDDEN")
        before = snapshot(self.root)
        with metadata_guard([root, self.root / "source"], [manifest]), mock.patch(
            "subprocess.run", side_effect=AssertionError("no Scout API")
        ):
            result = native.scan_provider("scout", [root])
            by_id = {item["workspaceId"]: item for item in result["catalog"]}
            self.assertEqual(native.local_paths(by_id["local-workspace"]), [str(local)])
            for key in ("cloud-workspace", "opaque", "fallback"):
                self.assertEqual(native.local_paths(by_id[key]), [])
        self.assertEqual(by_id["opaque"]["rootId"], "odsp:opaque-root-reference")
        self.assertEqual(by_id["opaque"]["nativeVersion"], 3)
        self.assertNotIn("FORBIDDEN", json.dumps(result))
        self.assertEqual(snapshot(self.root), before)

    def test_scout_version_shape_duplicate_ids_and_relative_root(self):
        root, path = self.scout([{"id": "x", "providerId": "local", "rootId": "../outside"}])
        self.assertEqual(native.local_paths(native.scan_provider("scout", [root])["catalog"][0]), [])
        for value in (
            {"version": 4, "workspaces": []},
            {"version": True, "workspaces": []},
            {"version": 3, "workspaces": [{"id": "x", "providerId": "local", "rootId": {}}]},
            {"version": 3, "workspaces": [
                {"id": "x", "providerId": "odsp", "rootId": "one"},
                {"id": "x", "providerId": "odsp", "rootId": "two"},
            ]},
        ):
            write_json(path, value)
            with self.subTest(value=value), self.assertRaises(RoutingError):
                native.scan_provider("scout", [root])

    def test_grokbot_app_only_no_persistence_read_or_workspace_claim(self):
        app = self.folder("Grokbot.app")
        support = self.folder(".grokbot")
        for root in (app, support):
            (root / "settings.json").write_text("FORBIDDEN")
            (root / "cache").mkdir()
            (root / "cache" / "opaque").write_text("FORBIDDEN")
        before = snapshot(self.root)
        with metadata_guard([app, support], []):
            result = native.scan_provider("grokbot", [app, support])
        self.assertEqual(result["catalog"], [])
        self.assertEqual(len(result["observations"]), 2)
        self.assertTrue(all(item["mapping"] == "workspace-mapping-unavailable" for item in result["observations"]))
        self.assertEqual(snapshot(self.root), before)
        with self.assertRaisesRegex(RoutingError, "grokbot-root-unrecognized"):
            native.scan_provider("grokbot", [self.folder("arbitrary-directory")])

    def test_bounds_count_file_bytes_total_bytes_time_and_profile_count(self):
        root, path = self.copilot()
        self.copilot(2)
        cases = [
            (Limits(max_entries=1), "count-bound"),
            (Limits(max_file_bytes=10), "file-size-bound"),
            (Limits(max_total_bytes=10), "byte-bound"),
        ]
        for limits, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(RoutingError, error):
                native.scan_provider("copilot", [root], limits=limits)
        with mock.patch.object(routing_io.time, "monotonic", side_effect=[0, 100]):
            with self.assertRaisesRegex(RoutingError, "time-bound"):
                native.scan_provider("copilot", [root])
        with self.assertRaisesRegex(RoutingError, "profile-count-bound"):
            native.scan_provider("copilot", [root] * 17)
        for values in ({"max_seconds": float("nan")}, {"batch_size": 0}, {"max_entries": 200001}, {"max_file_bytes": True}):
            with self.subTest(values=values), self.assertRaises(RoutingError):
                Limits(**values)

    def test_hermes_count_and_value_size_bounds(self):
        root, db = self.hermes("CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT);")
        db.executemany("INSERT INTO sessions VALUES (?, NULL)", [(str(n),) for n in range(3)])
        db.commit()
        db.close()
        with self.assertRaisesRegex(RoutingError, "count-bound"):
            native.scan_provider("hermes", [root], limits=Limits(max_entries=2))
        db = sqlite3.connect(root / "state.db")
        db.execute("UPDATE sessions SET cwd = ?", ("x" * 9000,))
        db.commit()
        db.close()
        with self.assertRaisesRegex(RoutingError, "schema-mismatch"):
            native.scan_provider("hermes", [root])

    def test_metadata_leaf_parent_root_symlinks_and_traversal_refused(self):
        source = self.folder("source")
        root, path = self.copilot(cwd=source)
        content = path.read_text()
        target = self.root / "forbidden"
        target.write_text(content)
        path.unlink()
        path.symlink_to(target)
        with metadata_guard([target], []), self.assertRaises(RoutingError):
            native.scan_provider("copilot", [root])
        alias = self.root / "profile-link"
        alias.symlink_to(root, target_is_directory=True)
        with self.assertRaises(RoutingError):
            native.scan_provider("copilot", [alias])
        with self.assertRaisesRegex(RoutingError, "path-traversal"):
            native.scan_provider("copilot", [str(root) + "/../copilot-profile"])
        leaf = self.folder("leaf")
        parent = self.root / "parent-link"
        parent.symlink_to(leaf, target_is_directory=True)
        with self.assertRaises(RoutingError):
            native.scan_provider("grokbot", [parent / "missing"])

    def test_symlink_session_directory_is_not_traversed(self):
        root, _ = self.copilot()
        other = self.folder("forbidden")
        (other / "workspace.yaml").write_text("FORBIDDEN")
        (root / "session-state" / session_id(2)).symlink_to(other, target_is_directory=True)
        with metadata_guard([other], []):
            result = native.scan_provider("copilot", [root])
        self.assertEqual(len(result["catalog"]), 1)

    def test_all_other_provider_metadata_symlinks_refused(self):
        claude, index = self.claude(data={"version": 1, "entries": []})
        scout, manifest = self.scout([])
        hermes, db = self.hermes()
        db.close()
        for provider, root, path in (("claude", claude, index), ("scout", scout, manifest), ("hermes", hermes, hermes / "state.db")):
            target = path.with_name("forbidden-native-target")
            path.rename(target)
            path.symlink_to(target)
            with self.subTest(provider=provider), metadata_guard([target], []), self.assertRaises(RoutingError):
                native.scan_provider(provider, [root])

    def test_native_root_and_local_path_protection(self):
        for relative in (
            ".copilot", ".claude", ".hermes", ".scout/workspace", ".grokbot", ".grok/skills",
            "Library/Application Support/Grokbot", "Library/Caches/Grokbot",
            "Library/Preferences/com.grokbot", "Grokbot.app",
        ):
            path = self.folder(relative)
            self.assertIsNone(routing_io.verified_directory(str(path)))
        with self.assertRaisesRegex(RoutingError, "broad-native-root"):
            native.scan_provider("copilot", [Path.home()])
        with self.assertRaises(RoutingError):
            native.scan_provider("unrecognized", [self.root])

    def test_closed_pointer_union_rejects_unknown_versions_fields_and_cross_provider_identity(self):
        root, _ = self.copilot()
        item = native.scan_provider("copilot", [root])["catalog"][0]
        for mutation in (
            {"pointer_version": 3}, {"provider": "claude"}, {"prompt": "FORBIDDEN"},
            {"pointer_type": "generic-ai-session"}, {"nativeSessionId": "../escape"},
            {"pointer_type": []}, {"availability": "missing-metadata"},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(RoutingError):
                native.validate_pointer({**item, **mutation})
        with self.assertRaises(RoutingError):
            native.validate_pointer({**item, "metadata": {"summary": "FORBIDDEN"}})

    def test_unicode_byte_bound_and_invalid_surrogate_are_schema_errors(self):
        for value in ("\ud800", "界" * 2000):
            with self.subTest(value_length=len(value)), self.assertRaises(RoutingError):
                native.text(value)


if __name__ == "__main__":
    unittest.main()
