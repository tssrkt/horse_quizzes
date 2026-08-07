import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.site_config import load_site_config
from tools import build_site


ROOT = Path(__file__).resolve().parents[1]


class SiteConfigTests(unittest.TestCase):
    def test_repository_config_keeps_origin_and_base_path_independent(self):
        config = load_site_config(ROOT)
        self.assertEqual(config["origin"], "https://tssrkt.github.io")
        self.assertEqual(config["base_path"], "/horse_quizzes/")
        self.assertEqual(config["public_url"], f'{config["origin"]}{config["base_path"]}')

    def test_root_domain_build_has_no_github_pages_dependency(self):
        with tempfile.TemporaryDirectory(prefix=".root-domain-build-", dir=ROOT) as directory:
            output = Path(directory) / "site"
            with patch.dict(os.environ, {"SITE_ORIGIN": "https://example.com", "BASE_PATH": "/"}):
                config = load_site_config(ROOT)
                self.assertEqual(config["public_url"], "https://example.com/")
                build_site.build(output)
            html = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*.html"))
            javascript = (output / "js" / "site-config.js").read_text(encoding="utf-8")
            self.assertIn("https://example.com/v/anatomy/", html)
            self.assertNotIn("tssrkt.github.io", html)
            self.assertNotIn("/horse_quizzes/", html)
            self.assertNotIn("{{SITE_", html)
            self.assertIn("https://example.com/", javascript)
            self.assertNotIn("tssrkt.github.io", javascript)
            self.assertNotIn("horse_quizzes", javascript)


if __name__ == "__main__":
    unittest.main()
