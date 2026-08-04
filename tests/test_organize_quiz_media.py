import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from scripts import organize_quiz_media
from tools import build_site


class OrganizeQuizCoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        (self.root / "data" / "quizzes").mkdir(parents=True)
        (self.root / "img" / "covers").mkdir(parents=True)
        (self.root / "img" / "quiz").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def write_quiz(self, cover=...):
        quiz = {
            "slug": "test-quiz",
            "title": "Тест",
            "questions": [],
        }
        if cover is not ...:
            quiz["cover"] = cover
        path = self.root / "data" / "quizzes" / "test-quiz.json"
        path.write_text(json.dumps(quiz, ensure_ascii=False), encoding="utf-8")
        return path

    def organize(self):
        quizzes = organize_quiz_media.load_quizzes(self.root)
        references = organize_quiz_media.collect_original_reference_counts(quizzes)
        payloads = organize_quiz_media.read_source_bytes(self.root, references)
        final = organize_quiz_media.organize_quizzes(self.root, quizzes, payloads, False)
        organize_quiz_media.cleanup_unreferenced(self.root, final, False)
        return final

    def add_source_cover(self, name="uploaded.webp", content=b"new cover"):
        path = self.root / "img" / "covers" / name
        path.write_bytes(content)
        return f"img/covers/{name}"

    def read_quiz(self):
        return json.loads((self.root / "data" / "quizzes" / "test-quiz.json").read_text(encoding="utf-8"))

    def test_create_with_cover_and_add_cover_on_later_edit(self):
        for initial_cover in ("with-cover", "without-cover"):
            with self.subTest(initial_cover=initial_cover):
                source = self.add_source_cover(f"{initial_cover}.webp", initial_cover.encode())
                self.write_quiz(source if initial_cover == "with-cover" else ...)
                if initial_cover == "without-cover":
                    edited = self.read_quiz()
                    edited["cover"] = source
                    self.write_quiz(source)
                final = self.organize()
                self.assertEqual(self.read_quiz()["cover"], source)
                self.assertTrue((self.root / source).is_file())
                self.assertIn(PurePosixPath(source), final)

    def test_replace_existing_cover(self):
        old = self.add_source_cover("test-quiz.webp", b"old")
        self.write_quiz(old)
        replacement = self.add_source_cover("replacement.png", b"replacement")
        self.write_quiz(replacement)
        self.organize()
        self.assertEqual(self.read_quiz()["cover"], replacement)
        self.assertEqual((self.root / replacement).read_bytes(), b"replacement")
        self.assertFalse((self.root / "img" / "covers" / "test-quiz.webp").exists())

    def test_cover_filename_is_preserved_exactly_for_cms_uploads(self):
        for filename in ("english01.webp", "English_02.webp", "English-cover_03.final.webp"):
            with self.subTest(filename=filename):
                source = self.add_source_cover(filename, filename.encode())
                self.write_quiz(source)
                self.organize()
                self.assertEqual(self.read_quiz()["cover"], f"img/covers/{filename}")
                self.assertEqual((self.root / "img" / "covers" / filename).read_bytes(), filename.encode())

    def test_vocabulary_quiz_preserves_uploaded_cover_filename(self):
        directory = self.root / "data" / "vocabulary-quizzes"
        directory.mkdir(parents=True)
        source = self.add_source_cover("English_02.webp")
        path = directory / "english.json"
        path.write_text(json.dumps({"slug": "english", "type": "vocabulary", "cover": source}, ensure_ascii=False), encoding="utf-8")
        self.organize()
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["cover"], "img/covers/English_02.webp")
        self.assertTrue((self.root / "img" / "covers" / "English_02.webp").is_file())

    def test_remove_cover_clears_reference_and_file(self):
        self.add_source_cover("test-quiz.webp")
        self.write_quiz(...)
        self.organize()
        self.assertNotIn("cover", self.read_quiz())
        self.assertFalse((self.root / "img" / "covers" / "test-quiz.webp").exists())

    def test_vocabulary_without_questions_is_left_unchanged(self):
        path = self.root / "data" / "quizzes" / "test-vocabulary.json"
        vocabulary = {"slug": "test-vocabulary", "type": "vocabulary", "table": "../vocabulary/words.xlsx"}
        path.write_text(json.dumps(vocabulary, ensure_ascii=False), encoding="utf-8")
        before = path.read_bytes()
        self.organize()
        self.assertEqual(path.read_bytes(), before)

    def test_regular_quiz_without_questions_remains_invalid(self):
        path = self.root / "data" / "quizzes" / "broken.json"
        path.write_text(json.dumps({"slug": "broken"}), encoding="utf-8")
        with self.assertRaisesRegex(TypeError, "questions"):
            self.organize()


class CurrentCoverContractTests(unittest.TestCase):
    def test_every_cover_reference_matches_an_existing_file_exactly(self):
        root = Path(__file__).resolve().parents[1]
        for directory in (root / "data" / "quizzes", root / "data" / "vocabulary-quizzes"):
            for path in directory.glob("*.json"):
                quiz = json.loads(path.read_text(encoding="utf-8"))
                cover = quiz.get("cover")
                if cover:
                    self.assertTrue((root / cover).is_file(), f"{path}: отсутствует {cover}")

    def test_horse_genetics_2_cover_exists_and_reaches_catalog(self):
        root = Path(__file__).resolve().parents[1]
        quiz = json.loads((root / "data" / "quizzes" / "horse-genetics-2.json").read_text(encoding="utf-8"))
        expected = "img/covers/horse-genetics-2.webp"
        self.assertEqual(quiz["cover"], expected)
        self.assertTrue((root / expected).is_file())

        catalog_quiz = dict(quiz)
        catalog_quiz["content_version"] = "test-version"
        catalog = build_site.make_catalog([], [catalog_quiz])
        published = next(item for item in catalog["quizzes"] if item["slug"] == "horse-genetics-2")
        self.assertEqual(published["cover"], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
