"""Static contract tests for the isolated read-only container packaging."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ContainerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dockerfile = (ROOT / "Dockerfile.options-monitor").read_text()
        cls.compose = (ROOT / "compose.options-monitor.yml").read_text()
        cls.dockerignore = (ROOT / ".dockerignore").read_text()

    def test_dockerfile_is_minimal_arm64_capable_read_only_web_image(self):
        self.assertRegex(
            self.dockerfile,
            r"FROM python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}",
        )
        self.assertIn("requirements-marketdata.txt", self.dockerfile)
        self.assertIn("USER options-monitor", self.dockerfile)
        self.assertIn('"--host", "0.0.0.0", "--port", "8765"', self.dockerfile)
        self.assertIn("research/four_leg_score/engine.py", self.dockerfile)
        self.assertNotIn("requirements.txt", self.dockerfile.replace("requirements-marketdata.txt", ""))

    def test_compose_has_internal_port_and_no_host_publication(self):
        self.assertIn("options-monitor:", self.compose)
        self.assertIn('expose:\n      - "8765"', self.compose)
        self.assertNotIn("\n    ports:", self.compose)
        self.assertIn("/api/v1/health", self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertIn("cap_drop:", self.compose)

    def test_build_context_excludes_secrets_state_and_unrelated_files(self):
        for pattern in (".git", "tests", "docs", ".env", "secrets", "output", "*.sqlite3"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, self.dockerignore)
        self.assertRegex(self.dockerignore, re.compile(r"research/four_leg_score", re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
