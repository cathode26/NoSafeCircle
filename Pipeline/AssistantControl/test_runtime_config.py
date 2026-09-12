"""Compose mapping generation only; no Docker or credentials accessed."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.runtime_config import compose_environment


class RuntimeConfigTests(unittest.TestCase):
    def test_external_mapping_preserves_base_and_override_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            checkout = root / "task"
            checkout.mkdir()
            (checkout / "compose.yaml").write_text("services: {}\n")
            (checkout / "compose.override.yaml").write_text("services: {}\n")
            run = root / "run"
            env = compose_environment(checkout, run, provider="claude", credential_volume="existing-claude")
            files = env["COMPOSE_FILE"].split(os.pathsep)
            self.assertEqual(3, len(files))
            config = json.loads(Path(files[-1]).read_text())
            self.assertEqual({"external": True, "name": "existing-claude"}, config["volumes"]["claude-config"])
            self.assertEqual(env, compose_environment(checkout, run, provider="claude", credential_volume="existing-claude"))
            with self.assertRaisesRegex(ValueError, "differs"):
                compose_environment(checkout, run, provider="claude", credential_volume="different-claude")


if __name__ == "__main__":
    unittest.main()
