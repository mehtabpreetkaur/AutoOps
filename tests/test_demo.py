import tempfile
import unittest
from pathlib import Path

from autoops.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_run_demo_shows_core_judge_walkthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_demo(Path(tmpdir) / "autoops-demo.db")

        self.assertIn("AutoOps Judge Demo", output)
        self.assertIn("Documents indexed: 19", output)
        self.assertIn("Contradictions:", output)
        self.assertIn("Connections refreshed: confluence, gitlab, jira", output)
        self.assertIn("Records seen: 8", output)
        self.assertIn("Safety allowed: False", output)
        self.assertIn("Live connectors are intentionally disabled", output)


if __name__ == "__main__":
    unittest.main()
