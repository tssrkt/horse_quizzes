import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_english_translation import import_package
from scripts.mark_stale_english_quizzes import mark_stale
from scripts.sync_english_quiz import SyncError, prepare


def russian_quiz():
    return {
        "title": "Породы", "slug": "breeds", "published": True, "publication_date": "2026-08-05",
        "difficulty": "low", "short_description": "Описание", "intro": "Вступление", "cover": "img/covers/breeds.webp",
        "tags": ["breeds", "history"], "questionImagesAlt": "Лошадь",
        "questions": [
            {"id": "question-01", "question": "Первый?", "image": "img/quiz/breeds/one.webp", "answers": [
                {"id": "answer-01", "text": "Да"}, {"id": "answer-02", "text": "Нет"}],
             "correct_answer_id": "answer-01", "explanation": "Первое пояснение"},
            {"id": "question-02", "question": "Второй?", "image": "", "answers": [
                {"id": "answer-01", "text": "Белый"}, {"id": "answer-02", "text": "Чёрный"}],
             "correct_answer_id": "answer-02", "explanation": "Второе пояснение"},
        ],
    }


class EnglishPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_dir = self.root / "data/quizzes"
        self.english_dir = self.root / "data/english-quizzes"
        self.package_dir = self.root / "data/translation-packages"
        self.source_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def save_source(self, source):
        path = self.source_dir / f"{source['slug']}.json"
        path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        return path

    def prepare(self, source=None):
        source = source or russian_quiz()
        return prepare(self.save_source(source), self.english_dir, self.package_dir)

    def translate_package(self, package_path):
        package = json.loads(package_path.read_text(encoding="utf-8"))
        package["status"] = "translated"
        package["fields"] = {key: f"EN:{value}" for key, value in package["fields"].items()}
        for question in package["questions"]:
            question["fields"] = {key: f"EN:{value}" for key, value in question["fields"].items()}
            for answer in question["answers"]:
                answer["text"] = f"EN:{answer['text']}"
        package_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        return package

    def create_and_import(self):
        target, package, mode, texts, automatic = self.prepare()
        self.translate_package(package)
        _, archived, _ = import_package(package, self.root)
        return target, archived, mode, texts, automatic

    def test_initial_prepare_creates_draft_and_full_text_only_package(self):
        target, package_path, mode, texts, _ = self.prepare()
        quiz = json.loads(target.read_text(encoding="utf-8"))
        package = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertEqual(mode, "created")
        self.assertFalse(quiz["published"])
        self.assertEqual(quiz["type"], "english")
        self.assertEqual(quiz["tags"], ["english", "breeds", "history"])
        self.assertEqual(quiz["questions"][0]["image"], "img/quiz/breeds/one.webp")
        self.assertEqual(quiz["questions"][0]["correct_answer_id"], "answer-01")
        self.assertEqual(package["fields"]["title"], "Породы")
        self.assertEqual(len(package["questions"]), 2)
        self.assertNotIn("tags", package["fields"])
        self.assertNotIn("difficulty", package["fields"])
        self.assertTrue(texts)
        self.assertIn("Do not change JSON keys", package["translation_instructions"])

    def test_deleted_target_with_stale_source_link_is_recreated(self):
        source = russian_quiz()
        source["english_quiz"] = "breeds-en"
        target, package_path, mode, texts, _ = self.prepare(source)
        recreated = json.loads(target.read_text(encoding="utf-8"))
        package = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertEqual(mode, "created")
        self.assertEqual(recreated["source_quiz"], "breeds")
        self.assertEqual(recreated["slug"], "breeds-en")
        self.assertEqual(recreated["_pending_translation"]["package"], "breeds-en.json")
        self.assertEqual(package["mode"], "created")
        self.assertTrue(texts)

    def test_empty_optional_question_images_alt_imports(self):
        source = russian_quiz()
        source["questionImagesAlt"] = ""
        target, package, *_ = self.prepare(source)
        translated = self.translate_package(package)
        translated["fields"]["questionImagesAlt"] = ""
        translated["fields"]["title"] = "Horse Breeds"
        package.write_text(json.dumps(translated, ensure_ascii=False), encoding="utf-8")
        imported_target, _, _ = import_package(package, self.root)
        quiz = json.loads(imported_target.read_text(encoding="utf-8"))
        self.assertEqual(quiz["questionImagesAlt"], "")
        self.assertEqual(quiz["title"], "Horse Breeds")

    def test_empty_required_quiz_and_answer_text_are_rejected(self):
        self.assert_rejected_without_target_change(lambda p: p["fields"].update(title=""), "non-empty")
        self.assert_rejected_without_target_change(
            lambda p: p["questions"][0]["answers"][0].update(text=""), "non-empty"
        )

    def test_valid_import_applies_text_and_marks_current(self):
        target, package, *_ = self.prepare()
        translated = self.translate_package(package)
        target_path, archived, imported = import_package(package, self.root)
        quiz = json.loads(target_path.read_text(encoding="utf-8"))
        self.assertIn("title", imported)
        self.assertEqual(quiz["title"], translated["fields"]["title"])
        self.assertEqual(quiz["translation_status"], "current")
        self.assertNotIn("_pending_translation", quiz)
        self.assertFalse(package.exists())
        self.assertEqual(archived.parent, self.package_dir / "imported")
        self.assertIn("breeds-en.", archived.name)
        self.assertEqual(json.loads(archived.read_text(encoding="utf-8"))["status"], "imported")

    def test_incremental_package_contains_only_changed_text_and_preserves_manual_edits(self):
        target, _, *_ = self.create_and_import()
        english = json.loads(target.read_text(encoding="utf-8"))
        english["title"] = "Manual title"
        english["questions"][0]["question"] = "Manual question"
        target.write_text(json.dumps(english, ensure_ascii=False), encoding="utf-8")
        source = json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))
        source["short_description"] = "Новое описание"
        _, package, mode, texts, _ = self.prepare(source)
        payload = json.loads(package.read_text(encoding="utf-8"))
        self.assertEqual(mode, "updated")
        self.assertEqual(payload["fields"], {"short_description": "Новое описание"})
        self.assertEqual(payload["questions"], [])
        self.assertEqual(texts, ["short_description"])
        self.translate_package(package)
        import_package(package, self.root)
        updated = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(updated["title"], "Manual title")
        self.assertEqual(updated["questions"][0]["question"], "Manual question")
        self.assertEqual(updated["short_description"], "EN:Новое описание")

    def test_nontext_and_structural_changes_sync_by_id_without_translation(self):
        target, _, *_ = self.create_and_import()
        source = json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))
        source["tags"] = ["genetics"]
        source["questions"][0]["image"] = "img/quiz/breeds/new.webp"
        removed = source["questions"].pop(1)
        added = copy.deepcopy(removed)
        added["id"] = "question-03"
        source["questions"].insert(0, added)
        _, package, _, _, automatic = self.prepare(source)
        quiz = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(quiz["tags"], ["english", "genetics"])
        self.assertEqual([q["id"] for q in quiz["questions"]], ["question-03", "question-01"])
        self.assertEqual(quiz["questions"][1]["image"], "img/quiz/breeds/new.webp")
        self.assertTrue(any("removed question: question-02" == item for item in automatic))
        self.assertTrue(any("added question #1: question-03" == item for item in automatic))
        payload = json.loads(package.read_text(encoding="utf-8"))
        self.assertEqual([q["id"] for q in payload["questions"]], ["question-03"])

    def test_question_and_answer_reordering_uses_stable_ids(self):
        target, _, *_ = self.create_and_import()
        before = json.loads(target.read_text(encoding="utf-8"))
        expected_text = before["questions"][0]["answers"][1]["text"]
        source = json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))
        source["questions"].reverse()
        source["questions"][1]["answers"].reverse()
        _, _, mode, texts, automatic = self.prepare(source)
        updated = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(mode, "updated")
        self.assertEqual(texts, [])
        self.assertIn("question order", automatic)
        self.assertIn("answer order: question-01", automatic)
        self.assertEqual(updated["questions"][1]["answers"][0]["id"], "answer-02")
        self.assertEqual(updated["questions"][1]["answers"][0]["text"], expected_text)

    def test_unchanged_prepare_does_not_replace_package(self):
        _, archived, *_ = self.create_and_import()
        before = archived.read_bytes()
        _, _, mode, texts, automatic = prepare(self.source_dir / "breeds.json", self.english_dir, self.package_dir)
        self.assertEqual((mode, texts, automatic), ("unchanged", [], []))
        self.assertEqual(archived.read_bytes(), before)

    def test_source_change_marks_translation_outdated(self):
        target, _, *_ = self.create_and_import()
        source = json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))
        source["intro"] = "Изменено"
        self.save_source(source)
        self.assertEqual(mark_stale(self.root), [target])
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["translation_status"], "outdated")

    def assert_rejected_without_target_change(self, mutate, message):
        target, package, *_ = self.prepare()
        payload = self.translate_package(package)
        mutate(payload)
        package.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        before = target.read_bytes()
        package_before = package.read_bytes()
        with self.assertRaisesRegex((SyncError, json.JSONDecodeError), message):
            import_package(package, self.root)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(package.read_bytes(), package_before)
        self.assertFalse((self.package_dir / "imported").exists())

    def test_changed_id_and_structure_are_rejected_without_partial_write(self):
        self.assert_rejected_without_target_change(lambda p: p["questions"][0].update(id="wrong"), "Question IDs")

    def test_missing_and_duplicate_answer_ids_are_rejected(self):
        self.assert_rejected_without_target_change(lambda p: p["questions"][0]["answers"].pop(), "answer IDs")

    def test_unknown_top_level_key_is_rejected(self):
        self.assert_rejected_without_target_change(lambda p: p.update(unexpected=True), "top-level keys")

    def test_package_for_another_quiz_is_rejected(self):
        self.assert_rejected_without_target_change(lambda p: p.update(source_quiz="other"), "source does not exist|another quiz")

    def test_stale_revision_is_rejected(self):
        target, package, *_ = self.prepare()
        self.translate_package(package)
        source = json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))
        source["intro"] = "Позднее изменение"
        self.save_source(source)
        before = target.read_bytes()
        with self.assertRaisesRegex(SyncError, "changed after"):
            import_package(package, self.root)
        self.assertEqual(target.read_bytes(), before)

    def test_damaged_json_and_repeat_import_are_rejected(self):
        _, archived, *_ = self.create_and_import()
        with self.assertRaisesRegex(SyncError, "Archived translation packages cannot be imported again"):
            import_package(archived, self.root)
        replay = self.package_dir / "replay.json"
        replay.write_bytes(archived.read_bytes())
        with self.assertRaisesRegex(SyncError, "already been imported"):
            import_package(replay, self.root)
        package = self.package_dir / "broken.json"
        package.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            import_package(package, self.root)

if __name__ == "__main__":
    unittest.main()
