import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import save_secret


def fake_run(clipboard: str, calls: list):
    def run(cmd, **kwargs):
        calls.append(cmd)
        out = clipboard if cmd == ["pbpaste"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out)
    return run


class SaveSecretTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "secrets.toml"
        self.path.write_text('ANTHROPIC_API_KEY = "old"\nJUSO_COORD_KEY = "stale"\n', encoding="utf-8")
        patcher = mock.patch.object(save_secret, "SECRETS", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def test_replaces_existing_key_backs_up_and_clears_clipboard(self):
        calls: list = []
        with mock.patch.object(save_secret.subprocess, "run", fake_run("U01TX0FVVEgyMDI2MTEwNjA0MTUxMjM0NTY=", calls)):
            self.assertEqual(save_secret.main(["JUSO_COORD_KEY"]), 0)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn('ANTHROPIC_API_KEY = "old"', text)
        self.assertEqual(text.count("JUSO_COORD_KEY"), 1)
        self.assertIn('JUSO_COORD_KEY = "U01TX0FVVEgyMDI2MTEwNjA0MTUxMjM0NTY="', text)
        backups = list(self.path.parent.glob("secrets.toml.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("stale", backups[0].read_text(encoding="utf-8"))
        self.assertIn(["pbcopy"], calls)

    def test_rejects_clipboard_that_is_not_a_key(self):
        before = self.path.read_text(encoding="utf-8")
        with mock.patch.object(save_secret.subprocess, "run", fake_run("안녕 이건 키가 아니야", [])):
            self.assertEqual(save_secret.main(["JUSO_SEARCH_KEY"]), 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_rejects_bad_name(self):
        self.assertEqual(save_secret.main(["juso key"]), 2)


if __name__ == "__main__":
    unittest.main()
