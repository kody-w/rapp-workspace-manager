import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "workspace_manager.py"
SPEC = importlib.util.spec_from_file_location("workspace_manager", MODULE_PATH)
workspace_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace_manager)


class FakeRapp:
    @staticmethod
    def rappid_valid(value):
        return isinstance(value, str) and value.startswith("rappid:@") and len(value.rsplit(":", 1)[-1]) == 64


class WorkspaceManagerTests(unittest.TestCase):
    def test_discovers_nested_git_roots_without_copying_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain = root / "plain"
            nested = plain / "nested"
            rapp = root / "rapp"
            for path in (plain, nested, rapp):
                (path / ".git").mkdir(parents=True)
            (rapp / "rappid.json").write_text(
                json.dumps(
                    {
                        "schema": "rapp/1",
                        "kind": "workspace",
                        "rappid": "rappid:@owner/workspace:" + "a" * 64,
                        "mode": "solo",
                        "world_id": "test-world",
                        "tags": ["test"],
                    }
                ),
                encoding="utf-8",
            )
            (plain / "secret.txt").write_text("must not enter registry", encoding="utf-8")

            paths = workspace_manager.discover_git_workspaces(root)
            pointers = [
                workspace_manager.read_workspace_pointer(path, FakeRapp)
                for path in paths
            ]
            encoded = json.dumps(pointers)

            expected = sorted(
                [nested.resolve(), plain.resolve(), rapp.resolve()],
                key=lambda path: str(path).casefold(),
            )
            self.assertEqual(paths, expected)
            self.assertNotIn("must not enter registry", encoded)
            rapp_pointer = next(pointer for pointer in pointers if pointer["name"] == "rapp")
            self.assertEqual(rapp_pointer["kind"], "rapp-workspace")
            self.assertEqual(rapp_pointer["world_id"], "test-world")

    def test_rejects_symlinked_or_invalid_rapp_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside.json"
            outside.write_text(
                json.dumps(
                    {
                        "schema": "rapp/1",
                        "kind": "workspace",
                        "rappid": "not-a-rappid",
                    }
                ),
                encoding="utf-8",
            )
            linked = root / "linked"
            linked.mkdir()
            (linked / "rappid.json").symlink_to(outside)
            invalid = root / "invalid"
            invalid.mkdir()
            (invalid / "rappid.json").write_text(outside.read_text(encoding="utf-8"))

            self.assertEqual(
                workspace_manager.read_workspace_pointer(linked, FakeRapp)["kind"],
                "git",
            )
            self.assertEqual(
                workspace_manager.read_workspace_pointer(invalid, FakeRapp)["kind"],
                "git",
            )

    def test_home_is_a_projection_of_pointer_metadata(self):
        identity = {
            "rappid": "rappid:@owner/manager:" + "b" * 64,
            "world_id": "routing",
        }
        registry = {
            "generated_utc": "2026-01-01T00:00:00.000Z",
            "workspaces": [
                {
                    "name": "alpha",
                    "path": "/tmp/alpha",
                    "kind": "git",
                    "mode": None,
                    "tags": [],
                }
            ],
        }
        home = workspace_manager.render_home(identity, registry)
        self.assertIn("PRIVATE / NEVER PUBLISH", home)
        self.assertIn("/tmp/alpha", home)
        self.assertIn("pointers only", home)


if __name__ == "__main__":
    unittest.main()
