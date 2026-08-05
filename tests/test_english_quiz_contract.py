import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools import build_site


ROOT = Path(__file__).resolve().parents[1]


class EnglishQuizContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".english-test-", dir=ROOT)
        self.data = Path(self.temp.name) / "data"
        shutil.copytree(ROOT / "data", self.data)
        (self.data / "english-quizzes").mkdir(exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def write_pair(self):
        source_path = self.data / "quizzes/horse-colors.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        english = json.loads(json.dumps(source))
        english.update({"type": "english", "slug": "horse-colors-en", "source_quiz": source["slug"], "published": False,
                        "title": "Horse colours", "short_description": "English description", "intro": "English intro",
                        "tags": ["english", *[tag for tag in source["tags"] if tag != "english"]],
                        "translation_status": "current", "source_content_hash": "a" * 64, "_translation_source": {"questions": []}})
        source["english_quiz"] = english["slug"]
        source_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        english_path = self.data / "english-quizzes/horse-colors-en.json"
        english_path.write_text(json.dumps(english, ensure_ascii=False), encoding="utf-8")
        return source_path, english_path

    def load(self):
        _, known = build_site.load_tags(self.data)
        return build_site.load_quizzes(self.data, known)

    def test_english_quiz_uses_regular_engine_and_cross_links(self):
        _, english_path = self.write_pair()
        quizzes = self.load()
        english = next(item for item in quizzes if item["slug"] == "horse-colors-en")
        self.assertEqual(english["type"], "english")
        self.assertTrue(english["questions"])
        self.assertEqual(english["source_quiz"], "horse-colors")
        self.assertNotIn("_translation_source", english)
        self.assertEqual(english_path.parent.name, "english-quizzes")

    def test_duplicate_source_and_missing_backlink_are_rejected(self):
        source_path, english_path = self.write_pair()
        duplicate = json.loads(english_path.read_text(encoding="utf-8"))
        duplicate["slug"] = "horse-colors-en-2"
        (english_path.parent / "horse-colors-en-2.json").write_text(json.dumps(duplicate), encoding="utf-8")
        with self.assertRaisesRegex(build_site.ContentError, "уже существует английская версия"):
            self.load()
        (english_path.parent / "horse-colors-en-2.json").unlink()
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source.pop("english_quiz")
        source_path.write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaisesRegex(build_site.ContentError, "ссылаться обратно"):
            self.load()


if __name__ == "__main__":
    unittest.main()
