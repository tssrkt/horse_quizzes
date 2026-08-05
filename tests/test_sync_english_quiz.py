import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.mark_stale_english_quizzes import mark_stale
from scripts.sync_english_quiz import SyncError, snapshot_hash, source_snapshot, sync


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


def fake_translate(items):
    return {key: f"EN:{value}" for key, value in items.items()}


class SyncEnglishQuizTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_dir = self.root / "data/quizzes"
        self.output_dir = self.root / "data/english-quizzes"
        self.source_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def save_source(self, source):
        path = self.source_dir / f"{source['slug']}.json"
        path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        return path

    def test_creates_draft_with_links_tags_images_ids_and_translations(self):
        source = russian_quiz()
        path, mode, changes = sync(self.save_source(source), self.output_dir, fake_translate)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(mode, "created")
        self.assertTrue(changes)
        self.assertEqual(path.name, "breeds-en.json")
        self.assertEqual(data["type"], "english")
        self.assertEqual(data["source_quiz"], "breeds")
        self.assertFalse(data["published"])
        self.assertEqual(data["tags"], ["english", "breeds", "history"])
        self.assertEqual(data["questions"][0]["id"], "question-01")
        self.assertEqual(data["questions"][0]["answers"][0]["id"], "answer-01")
        self.assertEqual(data["questions"][0]["correct_answer_id"], "answer-01")
        self.assertEqual(data["questions"][0]["image"], source["questions"][0]["image"])
        self.assertEqual(data["title"], "EN:Породы")
        self.assertEqual(data["source_content_hash"], snapshot_hash(source_snapshot(source)))
        self.assertEqual(json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))["english_quiz"], "breeds-en")

    def test_incremental_update_preserves_unmodified_manual_edits(self):
        source = russian_quiz()
        path, _, _ = sync(self.save_source(source), self.output_dir, fake_translate)
        english = json.loads(path.read_text(encoding="utf-8"))
        english["title"] = "Hand-edited title"
        english["questions"][0]["question"] = "Hand-edited question"
        english["questions"][0]["answers"][0]["text"] = "Hand-edited answer"
        path.write_text(json.dumps(english, ensure_ascii=False), encoding="utf-8")
        source["short_description"] = "Новое описание"
        self.save_source(source)

        _, mode, changes = sync(self.source_dir / "breeds.json", self.output_dir, fake_translate)
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(mode, "updated")
        self.assertIn("quiz field: short_description", changes)
        self.assertEqual(updated["short_description"], "EN:Новое описание")
        self.assertEqual(updated["title"], "Hand-edited title")
        self.assertEqual(updated["questions"][0]["question"], "Hand-edited question")
        self.assertEqual(updated["questions"][0]["answers"][0]["text"], "Hand-edited answer")

    def test_updates_changed_answer_image_tags_and_structure_by_id(self):
        source = russian_quiz()
        path, _, _ = sync(self.save_source(source), self.output_dir, fake_translate)
        source["tags"] = ["genetics"]
        source["questions"][0]["answers"][1]["text"] = "Никогда"
        source["questions"][0]["image"] = "img/quiz/breeds/new.webp"
        removed = source["questions"].pop(1)
        added = copy.deepcopy(removed)
        added.update(id="question-03", question="Третий?")
        source["questions"].insert(0, added)
        self.save_source(source)
        _, _, changes = sync(self.source_dir / "breeds.json", self.output_dir, fake_translate)
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(updated["tags"], ["english", "genetics"])
        self.assertEqual([q["id"] for q in updated["questions"]], ["question-03", "question-01"])
        self.assertEqual(updated["questions"][1]["image"], "img/quiz/breeds/new.webp")
        self.assertEqual(updated["questions"][1]["answers"][1]["text"], "EN:Никогда")
        self.assertTrue(any("removed question: question-02" == item for item in changes))
        self.assertTrue(any("added question #1: question-03" == item for item in changes))

    def test_no_changes_makes_no_translation_call(self):
        source = russian_quiz()
        path, _, _ = sync(self.save_source(source), self.output_dir, fake_translate)
        before = path.read_bytes()
        path2, mode, changes = sync(self.source_dir / "breeds.json", self.output_dir, lambda _: self.fail("translator called"))
        self.assertEqual((path2, mode, changes), (path, "unchanged", []))
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_versions_are_rejected(self):
        source = russian_quiz()
        self.save_source(source)
        self.output_dir.mkdir()
        for name in ("one.json", "two.json"):
            (self.output_dir / name).write_text(json.dumps({"source_quiz": "breeds"}), encoding="utf-8")
        with self.assertRaisesRegex(SyncError, "Duplicate"):
            sync(self.source_dir / "breeds.json", self.output_dir, fake_translate)

    def test_source_change_marks_translation_outdated(self):
        source = russian_quiz()
        path, _, _ = sync(self.save_source(source), self.output_dir, fake_translate)
        saved_source = json.loads((self.source_dir / "breeds.json").read_text(encoding="utf-8"))
        saved_source["questions"][0]["question"] = "Изменено?"
        self.save_source(saved_source)
        self.assertEqual(mark_stale(self.root), [path])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["translation_status"], "outdated")


if __name__ == "__main__":
    unittest.main()
