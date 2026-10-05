"""Inactive exports must not point alerts at an unverified external workflow."""

import json
import unittest
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


class ErrorWorkflowContractTests(unittest.TestCase):
    def test_exports_require_a_user_owned_error_workflow_at_install(self):
        paths = sorted(WORKFLOWS.glob("*.json"))
        self.assertEqual(len(paths), 9)
        for path in paths:
            with self.subTest(workflow=path.name):
                workflow = json.loads(path.read_text())
                self.assertFalse(workflow["active"])
                self.assertNotIn("errorWorkflow", workflow["settings"])


if __name__ == "__main__":
    unittest.main()
