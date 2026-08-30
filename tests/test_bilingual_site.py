import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_site


class BilingualSiteTests(unittest.TestCase):
    def build(self, base_path):
        temporary = tempfile.TemporaryDirectory(prefix=".bilingual-", dir=build_site.ROOT)
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site"
        with mock.patch.dict(os.environ, {"BASE_PATH": base_path, "SITE_ORIGIN": "https://example.test"}):
            build_site.build(output)
        return output

    def assert_build(self, base_path):
        output = self.build(base_path)
        for relative in ("index.html", "quizzes.html", "contacts.html", "en/index.html", "en/quizzes.html", "en/contacts.html", "en/v/horse-breeds/index.html"):
            self.assertTrue((output / relative).is_file(), relative)
        self.assertFalse((output / "en/v/horse-breeds-en").exists())
        catalog = json.loads((output / "data/catalog-en.json").read_text(encoding="utf-8"))
        self.assertTrue(catalog["quizzes"])
        self.assertEqual({quiz["type"] for quiz in catalog["quizzes"]}, {"english"})
        self.assertTrue(all(quiz["published"] and quiz["public_slug"] == quiz["source_quiz"] for quiz in catalog["quizzes"]))
        self.assertNotIn("english", {tag["slug"] for tag in catalog["tags"]})
        page = (output / "en/v/horse-breeds/index.html").read_text(encoding="utf-8")
        root = f"https://example.test{base_path}"
        self.assertIn('<html lang="en">', page)
        self.assertIn(f'<link rel="canonical" href="{root}en/v/horse-breeds/">', page)
        self.assertIn(f'hreflang="ru" href="{root}v/horse-breeds/"', page)
        self.assertIn('../../../v/horse-breeds/', page)
        russian = (output / "v/horse-breeds/index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="ru">', russian)
        self.assertIn('../../en/v/horse-breeds/', russian)
        untranslated = next(quiz for quiz in json.loads((output / "data/catalog.json").read_text(encoding="utf-8"))["quizzes"] if quiz.get("type") not in {"english", "vocabulary"} and not (output / "en/v" / quiz["slug"]).exists())
        no_translation_page = (output / "v" / untranslated["slug"] / "index.html").read_text(encoding="utf-8")
        self.assertIn('../../en/quizzes.html', no_translation_page)
        return output

    def test_github_pages_base_path(self):
        self.assert_build("/horse_quizzes/")

    def test_root_base_path(self):
        self.assert_build("/")

    def test_english_template_has_no_russian_catalog_mode(self):
        page = (build_site.ROOT / "en/quizzes.html").read_text(encoding="utf-8")
        self.assertNotIn("Английский для конников", page)
        self.assertNotIn("vocabulary", page)
        for text in ("Choose a Quiz", "By date", "By difficulty", "Alphabetical", "Loading quizzes"):
            self.assertIn(text, page)


if __name__ == "__main__":
    unittest.main()
