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
import routing_io
import workspace_manager as manager
from routing_io import RoutingError
from support import fixture_directory, metadata_guard, snapshot, write_json
from test_federation import FakeRapp


class RecursiveEstateTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_directory()
        self.root = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.workspace = self.root / "manager"
        self.command("init", "--workspace", self.workspace, "--owner", "synthetic")

    def command(self, *arguments):
        parsed = manager.parser().parse_args(list(map(str, arguments)))
        with mock.patch.object(manager, "find_rapp1", return_value=self.root):
            with mock.patch.object(manager, "load_rapp", return_value=FakeRapp):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    result = parsed.run(parsed)
        return result, output.getvalue()

    def folder(self, relative):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def registry(self):
        return manager.load_registry(self.workspace)

    def view(self, filename=None):
        registry = self.registry()
        path = self.workspace / (filename or registry["editor_view"])
        return json.loads(path.read_text())

    def select(self, *paths):
        arguments = ["estate", "--workspace", self.workspace]
        for path in paths:
            arguments.extend(["--root", path])
        self.command(*arguments)

    def add_group(self, group_id, name, parent=None):
        arguments = [
            "group", "add", "--workspace", self.workspace,
            "--id", group_id, "--name", name,
        ]
        if parent is not None:
            arguments.extend(["--parent", parent])
        return self.command(*arguments)

    def assign(self, group_id, path, alias=None):
        arguments = [
            "group", "assign", "--workspace", self.workspace,
            "--id", group_id, "--path", path,
        ]
        if alias is not None:
            arguments.extend(["--alias", alias])
        return self.command(*arguments)

    def test_legacy_load_synthesizes_default_overlay_without_writing_or_reminting(self):
        registry_path = self.workspace / "registry.json"
        identity_path = self.workspace / "rappid.json"
        legacy = json.loads(registry_path.read_text())
        legacy.pop("organization")
        write_json(registry_path, legacy)
        registry_before = registry_path.read_bytes()
        identity_before = identity_path.read_bytes()

        loaded = manager.load_registry(self.workspace)

        self.assertEqual(loaded["organization"], manager.default_organization())
        self.assertEqual(registry_path.read_bytes(), registry_before)
        self.assertEqual(identity_path.read_bytes(), identity_before)
        self.assertEqual(loaded["manager_rappid"], legacy["manager_rappid"])

    def test_organization_schema_rejects_unknowns_cycles_orphans_and_bad_pointers(self):
        source = self.folder("source/project")
        self.select(source)
        base = self.registry()
        pointer_id = base["workspaces"][0]["pointer_id"]
        unknown_pointer = "local:" + "f" * 64

        invalid = []
        value = copy.deepcopy(base)
        value["organization"]["unexpected"] = True
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["groups"][0]["unexpected"] = True
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["groups"].append(
            {"id": "root", "name": "Duplicate", "parent": "root"}
        )
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["groups"].append(
            {"id": "orphan", "name": "Orphan", "parent": "missing"}
        )
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["groups"].extend([
            {"id": "one", "name": "One", "parent": "two"},
            {"id": "two", "name": "Two", "parent": "one"},
        ])
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["groups"].append(
            {"id": "Not Valid", "name": "Invalid ID", "parent": "root"}
        )
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["groups"].append(
            {"id": "bad-name", "name": " trailing ", "parent": "root"}
        )
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["aliases"] = [
            {"pointer_id": unknown_pointer, "alias": "unknown"}
        ]
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["placements"] = [
            {"pointer_id": unknown_pointer, "group_id": "root"}
        ]
        invalid.append(value)
        value = copy.deepcopy(base)
        value["organization"]["placements"] = [
            {"pointer_id": pointer_id, "group_id": "root"},
            {"pointer_id": pointer_id, "group_id": "root"},
        ]
        invalid.append(value)

        for registry in invalid:
            with self.subTest(organization=registry["organization"]):
                with self.assertRaises(RoutingError):
                    manager.validate_registry(registry)

    def test_recursive_group_focus_tree_and_manager_first_behavior(self):
        api = self.folder("source/api")
        web = self.folder("source/web")
        notes = self.folder("source/notes")
        self.select(api, web, notes)
        self.add_group("platform", "Platform")
        self.add_group("services", "Services", "platform")
        self.assign("services", api, "api-service")
        self.assign("platform", web)

        _, first_tree = self.command("tree", "--workspace", self.workspace)
        _, second_tree = self.command("tree", "--workspace", self.workspace)
        self.assertEqual(first_tree, second_tree)
        self.assertLess(first_tree.index("Platform [platform]"), first_tree.index("Services [services]"))
        self.assertIn("api-service -> api", first_tree)
        self.assertIn("Unorganized", first_tree)
        self.assertIn("notes", first_tree)

        _, output = self.command(
            "focus", "--workspace", self.workspace, "--target", "platform"
        )
        focused = Path(output.strip())
        self.assertEqual(focused.name, "focus-group-platform.code-workspace")
        folders = self.view(focused.name)["folders"]
        self.assertEqual(folders[0]["path"], str(self.workspace))
        self.assertEqual({item["path"] for item in folders[1:]}, {str(api), str(web)})
        self.assertNotIn(str(notes), {item["path"] for item in folders})

        self.command("focus", "--workspace", self.workspace, "--target", "services")
        self.assertEqual(
            [item["path"] for item in self.view("focus-group-services.code-workspace")["folders"]],
            [str(self.workspace), str(api)],
        )
        with self.assertRaisesRegex(RoutingError, "group"):
            self.command(
                "focus", "--workspace", self.workspace,
                "--target", "platform", "--print-path",
            )

    def test_alias_open_focus_ambiguity_and_vscode_preference(self):
        one = self.folder("source/one")
        two = self.folder("source/two")
        self.select(one, two)
        self.assign("root", one, "quick")

        _, printed = self.command(
            "open", "--workspace", self.workspace, "--name", "quick", "--print-path"
        )
        self.assertEqual(printed.strip(), str(one))
        _, focus_output = self.command(
            "focus", "--workspace", self.workspace, "--target", "quick"
        )
        pointer_id = next(
            item["pointer_id"] for item in self.registry()["workspaces"]
            if item["path"] == str(one)
        )
        self.assertEqual(
            Path(focus_output.strip()).name,
            f"focus-local-{pointer_id.split(':', 1)[1]}.code-workspace",
        )
        self.assertEqual(
            [item["path"] for item in self.view(Path(focus_output.strip()).name)["folders"]],
            [str(self.workspace), str(one)],
        )

        with mock.patch.object(manager.shutil, "which", side_effect=lambda name: "/synthetic/code" if name == "code" else None):
            with mock.patch.object(manager.subprocess, "run") as run:
                self.command("open", "--workspace", self.workspace, "--name", "quick")
        run.assert_called_once_with(["code", "-n", str(one)], check=True)

        self.add_group("quick", "Quick Group")
        with self.assertRaisesRegex(RoutingError, "ambiguous"):
            self.command("focus", "--workspace", self.workspace, "--target", "quick")
        self.command("group", "remove", "--workspace", self.workspace, "--id", "quick")

        self.assign("root", two, "quick")
        with self.assertRaisesRegex(RoutingError, "ambiguous"):
            self.command(
                "open", "--workspace", self.workspace, "--name", "quick", "--print-path"
            )
        with self.assertRaisesRegex(RoutingError, "ambiguous"):
            self.command("focus", "--workspace", self.workspace, "--target", "quick")

    def test_group_remove_refuses_root_children_and_placements(self):
        source = self.folder("source/project")
        self.select(source)
        self.add_group("parent", "Parent")
        self.add_group("child", "Child", "parent")

        with self.assertRaisesRegex(RoutingError, "root"):
            self.command("group", "remove", "--workspace", self.workspace, "--id", "root")
        with self.assertRaisesRegex(RoutingError, "non-empty"):
            self.command("group", "remove", "--workspace", self.workspace, "--id", "parent")
        self.assign("child", source)
        with self.assertRaisesRegex(RoutingError, "non-empty"):
            self.command("group", "remove", "--workspace", self.workspace, "--id", "child")

        self.command("group", "unassign", "--workspace", self.workspace, "--path", source)
        self.command("group", "remove", "--workspace", self.workspace, "--id", "child")
        self.command("group", "remove", "--workspace", self.workspace, "--id", "parent")
        self.assertEqual(
            self.registry()["organization"]["groups"],
            [{"id": "root", "name": "Estate", "parent": None}],
        )

    def test_exact_and_recursive_scans_preserve_then_prune_overlay(self):
        exact = self.folder("source/exact")
        removed = self.folder("source/removed")
        self.select(exact, removed)
        self.add_group("active", "Active")
        self.assign("active", exact, "exact-alias")
        self.assign("active", removed, "removed-alias")
        removed_id = next(
            item["pointer_id"] for item in self.registry()["workspaces"]
            if item["path"] == str(removed)
        )
        self.command("focus", "--workspace", self.workspace, "--target", "removed-alias")
        workspace_focus = f"focus-local-{removed_id.split(':', 1)[1]}.code-workspace"
        before = copy.deepcopy(self.registry()["organization"])

        self.select(exact, removed)
        after = self.registry()["organization"]
        self.assertEqual(after["aliases"], before["aliases"])
        self.assertEqual(after["placements"], before["placements"])

        self.select(exact)
        after = self.registry()["organization"]
        self.assertEqual(
            {item["alias"] for item in after["aliases"]},
            {"exact-alias"},
        )
        self.assertEqual(len(after["placements"]), 1)
        self.assertEqual(
            next(item for item in after["focused_views"] if item["filename"] == workspace_focus)["target_type"],
            "empty",
        )
        self.assertEqual(
            self.view(workspace_focus)["folders"],
            [{"name": "RAPP Workspace Manager", "path": str(self.workspace)}],
        )

        discovered = self.folder("discovery/repository")
        (discovered / ".git").mkdir()
        scan_root = discovered.parent
        allowed = [discovered / "rappid.json"]
        with metadata_guard([scan_root], allowed):
            self.command("scan", "--workspace", self.workspace, "--root", scan_root)
        self.assign("active", discovered, "discovered-alias")
        discovered_before = copy.deepcopy(self.registry()["organization"])
        with metadata_guard([scan_root], allowed):
            self.command("scan", "--workspace", self.workspace, "--root", scan_root)
        self.assertEqual(
            self.registry()["organization"]["aliases"],
            discovered_before["aliases"],
        )
        (discovered / ".git").rmdir()
        with metadata_guard([scan_root], allowed):
            self.command("scan", "--workspace", self.workspace, "--root", scan_root)
        final = self.registry()["organization"]
        self.assertNotIn("discovered-alias", {item["alias"] for item in final["aliases"]})
        self.assertEqual(len(final["placements"]), 1)

    def test_replaced_directory_does_not_inherit_v2_organization_identity(self):
        source = self.folder("source/project")
        self.select(source)
        self.add_group("work", "Work")
        self.assign("work", source, "important")
        previous = self.registry()
        old_pointer = previous["workspaces"][0]
        replacement = {
            **old_pointer,
            "pointer_id": "local:" + "f" * 64,
            "filesystemIdentity": [
                old_pointer["filesystemIdentity"][0],
                old_pointer["filesystemIdentity"][1] + 1,
            ],
        }

        manager.replace_local_workspaces(previous, [replacement])

        self.assertEqual(previous["organization"]["aliases"], [])
        self.assertEqual(previous["organization"]["placements"], [])

    def test_case_equivalent_editor_names_are_refused(self):
        source = self.folder("source/project")
        self.select(source)
        registry = self.registry()
        registry["editor_views"].append("ESTATE.code-workspace")

        with self.assertRaisesRegex(RoutingError, "editor-view-schema"):
            manager.validate_registry(registry)

        with self.assertRaisesRegex(RoutingError, "conflicts-editor-view"):
            self.command(
                "focus", "--workspace", self.workspace,
                "--target", source.name,
                "--output", "ESTATE.code-workspace",
            )

    def test_focused_view_is_deterministic_atomic_and_preserves_owner_values(self):
        source = self.folder("source/project")
        self.select(source)
        self.add_group("work", "Work")
        self.assign("work", source)
        output = self.workspace / "work.code-workspace"
        output.write_text("""{
          // Owner values remain semantically intact.
          "settings": {"owner.setting": true,},
          "extensions": {"recommendations": ["owner.extension"],},
          "launch": {"version": "0.2.0", "configurations": [],},
          "folders": [{"path": "/obsolete"}],
        }""")

        self.command(
            "focus", "--workspace", self.workspace,
            "--target", "work", "--output", output,
        )
        first = output.read_bytes()
        value = json.loads(first)
        self.assertEqual(value["settings"], {"owner.setting": True})
        self.assertEqual(value["extensions"], {"recommendations": ["owner.extension"]})
        self.assertEqual(value["launch"], {"version": "0.2.0", "configurations": []})
        self.assertEqual(value["folders"][0]["path"], str(self.workspace))

        original_replace = os.replace
        replacements = []

        def replacing(src, dst, **kwargs):
            if dst == output.name:
                self.assertTrue(str(src).endswith(".pending"))
                self.assertEqual(output.read_bytes(), first)
                replacements.append(dst)
            return original_replace(src, dst, **kwargs)

        with mock.patch.object(routing_io.os, "replace", side_effect=replacing):
            self.command(
                "focus", "--workspace", self.workspace,
                "--target", "work", "--output", output,
            )
        self.assertEqual(replacements, [output.name])
        self.assertEqual(output.read_bytes(), first)

    def test_overlay_commands_and_home_never_mutate_or_read_source_content(self):
        source = self.folder("source/project")
        (source / "secret.txt").write_text("FORBIDDEN-SOURCE-CONTENT")
        self.select(source)
        before = snapshot(source)

        with metadata_guard([source], []):
            self.add_group("private-work", "Private Work")
            self.assign("private-work", source, "private-project")
            self.command("tree", "--workspace", self.workspace)
            self.command("focus", "--workspace", self.workspace, "--target", "private-work")
            self.command(
                "open", "--workspace", self.workspace,
                "--name", "private-project", "--print-path",
            )

        self.assertEqual(snapshot(source), before)
        home = (self.workspace / "HOME.md").read_text()
        self.assertIn("## Organization", home)
        self.assertIn("group add", home)
        self.assertIn("focus --workspace", home)
        self.assertNotIn("FORBIDDEN-SOURCE-CONTENT", home)


if __name__ == "__main__":
    unittest.main()
