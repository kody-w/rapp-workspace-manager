import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import check_conformance
from support import fixture_directory


class ConformanceTests(unittest.TestCase):
    def check(self, writer, canonical_verdict="COMPLIANT", findings=None):
        checker = SimpleNamespace(check_repo=lambda _: (canonical_verdict, findings or [], []))
        with fixture_directory() as root:
            with mock.patch.object(check_conformance.manager, "load_rapp", return_value=object()):
                with mock.patch.object(check_conformance, "load_tool", side_effect=[checker, writer]):
                    return check_conformance.check_repository(root, root)

    def test_identity_only_compliant_result_cannot_pass_without_existing_frames(self):
        writer = SimpleNamespace(all_slugs=lambda: [], verify_chain=lambda _: [])
        result = self.check(writer)
        self.assertEqual(result["frames_verified"], 0)
        self.assertEqual(result["verdict"], "DRIFT")
        self.assertEqual(result["findings"][0]["rule"], "nonzero-frame-evidence")

    def test_uses_existing_canonical_chain_verifier_and_records_nonzero_count(self):
        verify = mock.Mock(return_value=[{}, {}, {}, {}])
        writer = SimpleNamespace(all_slugs=lambda: ["example-stream"], verify_chain=verify)
        result = self.check(writer)
        self.assertEqual(result["verdict"], "COMPLIANT")
        self.assertEqual(result["frames_verified"], 4)
        self.assertEqual(result["streams_verified"], 1)
        verify.assert_called_once_with("example-stream")

    def test_failed_canonical_chain_or_identity_still_fails_conformance(self):
        writer = SimpleNamespace(
            all_slugs=lambda: ["broken"],
            verify_chain=mock.Mock(side_effect=SystemExit("canonical chain failure")),
        )
        result = self.check(writer)
        self.assertEqual(result["verdict"], "DRIFT")
        self.assertEqual(result["frames_verified"], 0)
        good = SimpleNamespace(all_slugs=lambda: ["good"], verify_chain=lambda _: [{}])
        result = self.check(good, "DRIFT", [{"rule": "identity mismatch"}])
        self.assertEqual(result["verdict"], "DRIFT")
        self.assertEqual(result["frames_verified"], 1)


if __name__ == "__main__":
    unittest.main()
