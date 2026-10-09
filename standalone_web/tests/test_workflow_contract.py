"""Static contract tests for the ARM64 GHCR publishing workflow."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "options-monitor-arm64-image.yml"


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()

    def test_workflow_triggers_on_final_branch_and_manual_dispatch(self):
        self.assertIn("feature/options-monitor-v1-final", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)

    def test_workflow_permissions_are_minimal_for_ghcr_publish(self):
        self.assertIn("contents: read", self.workflow)
        self.assertIn("packages: write", self.workflow)
        self.assertIn("GITHUB_TOKEN", self.workflow)

    def test_workflow_preserves_acceptance_checks(self):
        for command in (
            "python -m unittest discover -s research/four_leg_score -p 'test_*.py' -v",
            "python -m unittest discover -s standalone_web/tests -p 'test_*.py' -v",
            "python -m compileall -q standalone_web research/four_leg_score",
            "node --check standalone_web/static/app.js",
            "docker compose -f compose.options-monitor.yml config",
        ):
            with self.subTest(command=command):
                self.assertIn(command, self.workflow)

    def test_workflow_builds_and_publishes_commit_tagged_arm64_image_digest(self):
        self.assertIn("docker/setup-buildx-action", self.workflow)
        self.assertIn("docker/login-action", self.workflow)
        self.assertIn("docker/build-push-action", self.workflow)
        self.assertIn("platforms: linux/arm64", self.workflow)
        self.assertIn("push: true", self.workflow)
        self.assertIn("${{ github.sha }}", self.workflow)
        self.assertIn("steps.build.outputs.digest", self.workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", self.workflow)


if __name__ == "__main__":
    unittest.main()
