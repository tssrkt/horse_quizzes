import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools import build_site


ROOT = build_site.ROOT


class BuildSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".content-test-", dir=ROOT)
        self.base = Path(self.temp.name)
        self.data = self.base / "data"
        shutil.copytree(ROOT / "data", self.data)

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        tags, known = build_site.load_tags(self.data)
        quizzes = build_site.load_quizzes(self.data, known)
        return tags, quizzes

    def horse(self):
        return json.loads((self.data / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))

    def write_quiz(self, quiz, name="horse-colors.json"):
        (self.data / "quizzes" / name).write_text(json.dumps(quiz, ensure_ascii=False, indent=2), encoding="utf-8")

    def assert_quiz_error(self, mutate, expected):
        quiz = json.loads((ROOT / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        mutate(quiz)
        self.write_quiz(quiz)
        tags, known = build_site.load_tags(self.data)
        with self.assertRaisesRegex(build_site.ContentError, expected):
            build_site.load_quizzes(self.data, known)

    def test_auto_discovers_new_tag_and_quiz_but_excludes_draft(self):
        tag = {"name": "История", "slug": "history", "published": True}
        (self.data / "tags" / "history.json").write_text(json.dumps(tag, ensure_ascii=False), encoding="utf-8")
        draft = self.horse()
        draft.update({"slug": "history-draft", "title": "Черновик", "published": False, "tags": ["history"]})
        for question in draft["questions"]:
            question["image"] = ""
        self.write_quiz(draft, "history-draft.json")
        tags, quizzes = self.load()
        catalog = build_site.make_catalog(tags, quizzes)
        self.assertIn("history", {item["slug"] for item in catalog["tags"]})
        self.assertNotIn("history-draft", {item["slug"] for item in catalog["quizzes"]})
        draft["published"] = True
        self.write_quiz(draft, "history-draft.json")
        tags, quizzes = self.load()
        published = {item["slug"]: item for item in build_site.make_catalog(tags, quizzes)["quizzes"]}
        self.assertEqual(published["history-draft"]["question_count"], len(draft["questions"]))

    def test_discovers_vocabulary_cms_collection_without_questions(self):
        table = self.data / "vocabulary" / "cms-words.csv"
        table.parent.mkdir(exist_ok=True)
        table.write_text("English,Russian,Category\nhorse,лошадь,\nmare,кобыла,\n", encoding="utf-8")
        source = {
            "type": "vocabulary", "title": "CMS словарь", "slug": "cms-words", "published": False,
            "publication_date": "2026-08-04", "difficulty": "low", "short_description": "Описание",
            "intro": "Вступление", "cover": "", "tags": ["words"], "table": "../vocabulary/cms-words.csv"
        }
        directory = self.data / "vocabulary-quizzes"
        directory.mkdir(exist_ok=True)
        (directory / "cms-words.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        tags, quizzes = self.load()
        loaded = next(quiz for quiz in quizzes if quiz["slug"] == "cms-words")
        self.assertEqual(loaded["type"], "vocabulary")
        self.assertEqual(len(loaded["parts"]), 1)
        self.assertEqual(loaded["parts"][0]["title"], "Часть 1")
        self.assertEqual(loaded["parts"][0]["word_count"], 2)
        self.assertEqual(len(loaded["parts"][0]["vocabulary"]), 2)
        self.assertEqual(loaded["word_count"], 2)
        self.assertNotIn("vocabulary", loaded)
        self.assertNotIn("questions", loaded)
        self.assertNotIn("cms-words", {quiz["slug"] for quiz in build_site.make_catalog(tags, quizzes)["quizzes"]})

    def test_builds_independent_vocabulary_parts_and_total_count(self):
        vocabulary_dir = self.data / "vocabulary"
        vocabulary_dir.mkdir(exist_ok=True)
        (vocabulary_dir / "one.csv").write_text("English,Russian,Category\nhead,голова,body\nneck,шея,body\n", encoding="utf-8")
        (vocabulary_dir / "two.csv").write_text("English,Russian,Category\nsaddle,седло,body\nbridle,уздечка,body\n", encoding="utf-8")
        source = {
            "type": "vocabulary", "title": "Части", "slug": "parts-test", "published": True,
            "publication_date": "2026-08-04", "difficulty": "low", "short_description": "Описание",
            "intro": "Вступление", "cover": "", "tags": ["words"],
            "parts": [{"title": "", "table": "../vocabulary/one.csv"}, {"title": "Амуниция", "table": "../vocabulary/two.csv"}],
        }
        directory = self.data / "vocabulary-quizzes"
        directory.mkdir(exist_ok=True)
        (directory / "parts-test.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        tags, quizzes = self.load()
        loaded = next(quiz for quiz in quizzes if quiz["slug"] == "parts-test")
        self.assertEqual([part["title"] for part in loaded["parts"]], ["Часть 1", "Амуниция"])
        self.assertEqual([part["word_count"] for part in loaded["parts"]], [2, 2])
        self.assertEqual(loaded["word_count"], 4)
        self.assertEqual({word["english"] for word in loaded["parts"][0]["vocabulary"]}, {"head", "neck"})
        self.assertEqual({word["english"] for word in loaded["parts"][1]["vocabulary"]}, {"saddle", "bridle"})
        catalog = build_site.make_catalog(tags, quizzes)
        self.assertEqual(next(item for item in catalog["quizzes"] if item["slug"] == "parts-test")["question_count"], 4)

    def test_vocabulary_part_error_identifies_part_and_table(self):
        source = {
            "type": "vocabulary", "title": "Части", "slug": "broken-parts", "published": False,
            "publication_date": "2026-08-04", "difficulty": "low", "short_description": "Описание",
            "intro": "Вступление", "cover": "", "tags": ["words"],
            "parts": [{"title": "Проблемная", "table": "../vocabulary/missing.xlsx"}],
        }
        directory = self.data / "vocabulary-quizzes"
        directory.mkdir(exist_ok=True)
        (directory / "broken-parts.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(build_site.ContentError, r"parts\[1\].*Проблемная.*missing.xlsx"):
            self.load()

    def test_no_correct_answer(self):
        self.assert_quiz_error(lambda quiz: quiz["questions"][0].pop("correct_answer_id"), "требуется correct_answer_id")

    def test_correct_answer_must_reference_an_available_option(self):
        self.assert_quiz_error(lambda quiz: quiz["questions"][0].update(correct_answer_id="answer-99"), "отсутствует в answers")

    def test_editing_correct_and_incorrect_answer_text_keeps_selection(self):
        quiz = self.horse()
        self.assertGreaterEqual(len(quiz["questions"]), 24)
        question = quiz["questions"][23]
        selected = question["correct_answer_id"]
        correct = next(answer for answer in question["answers"] if answer["id"] == selected)
        incorrect = next(answer for answer in question["answers"] if answer["id"] != selected)
        correct["text"] += " (изменён правильный)"
        incorrect["text"] += " (изменён неправильный)"
        self.write_quiz(quiz)

        _, quizzes = self.load()
        loaded = next(item for item in quizzes if item["slug"] == "horse-colors")
        loaded_question = loaded["questions"][23]
        self.assertEqual(loaded_question["correct_answer_id"], selected)
        self.assertTrue(any(answer["text"].endswith("(изменён правильный)") for answer in loaded_question["answers"]))
        self.assertTrue(any(answer["text"].endswith("(изменён неправильный)") for answer in loaded_question["answers"]))

    def test_correct_answer_selection_survives_save_reopen_and_change(self):
        quiz = self.horse()
        question = quiz["questions"][23]
        original = question["correct_answer_id"]
        replacement = next(answer["id"] for answer in question["answers"] if answer["id"] != original)
        question["correct_answer_id"] = replacement
        self.write_quiz(quiz)

        reopened = self.horse()
        reopened_question = reopened["questions"][23]
        self.assertEqual(reopened_question["correct_answer_id"], replacement)
        self.assertTrue(all("correct" not in answer for answer in reopened_question["answers"]))

        _, quizzes = self.load()
        loaded = next(item for item in quizzes if item["slug"] == "horse-colors")
        self.assertEqual(loaded["questions"][23]["correct_answer_id"], replacement)

    def test_legacy_correct_flags_are_supported_and_normalized(self):
        quiz = self.horse()
        question = quiz["questions"][0]
        selected = question.pop("correct_answer_id")
        for answer in question["answers"]:
            answer["correct"] = answer["id"] == selected
        self.write_quiz(quiz)
        _, quizzes = self.load()
        loaded = next(item for item in quizzes if item["slug"] == "horse-colors")
        self.assertEqual(loaded["questions"][0]["correct_answer_id"], selected)
        self.assertTrue(all("correct" not in answer for answer in loaded["questions"][0]["answers"]))

    def test_invalid_and_duplicate_ids_are_rejected(self):
        self.assert_quiz_error(lambda quiz: quiz["questions"][0].update(id="manual"), "формат question-N")
        self.assert_quiz_error(lambda quiz: quiz["questions"][0]["answers"][0].update(id="manual"), "формат answer-N")
        self.assert_quiz_error(lambda quiz: quiz["questions"][1].update(id="question-01"), "конфликтующий ID вопроса «question-01»")
        self.assert_quiz_error(lambda quiz: quiz["questions"][0]["answers"][1].update(id="answer-01"), "конфликтующий ID ответа «answer-01»")

    def test_generates_stable_ids_and_content_version(self):
        _, quizzes = self.load()
        horse = next(quiz for quiz in quizzes if quiz["slug"] == "horse-colors")
        self.assertEqual(horse["questions"][0]["id"], "question-01")
        self.assertEqual(horse["questions"][4]["id"], "question-05")
        self.assertEqual([answer["id"] for answer in horse["questions"][0]["answers"]], ["answer-01", "answer-02", "answer-03", "answer-04"])
        self.assertRegex(horse["content_version"], r"^[0-9a-f]{64}$")

        changed = self.horse()
        changed["questions"][3]["question"] += " Изменено"
        self.write_quiz(changed)
        _, changed_quizzes = self.load()
        changed_horse = next(quiz for quiz in changed_quizzes if quiz["slug"] == "horse-colors")
        self.assertNotEqual(horse["content_version"], changed_horse["content_version"])

        image_changed = self.horse()
        replacement = self.base / "replacement.webp"
        replacement.write_bytes(b"replacement image bytes")
        image_changed["questions"][0]["image"] = replacement.relative_to(ROOT).as_posix()
        self.assertNotEqual(horse["content_version"], build_site.normalize_quiz(image_changed)["content_version"])

        changed = self.horse()
        changed["questions"].append(copy.deepcopy(changed["questions"][-1]))
        changed["questions"][-1]["id"] = f"question-{len(changed['questions']):02d}"
        changed["questions"][-1]["question"] = "Новый тестовый вопрос?"
        self.write_quiz(changed)
        _, changed_quizzes = self.load()
        changed_horse = next(quiz for quiz in changed_quizzes if quiz["slug"] == "horse-colors")
        self.assertEqual(len(changed_horse["questions"]), len(horse["questions"]) + 1)
        self.assertNotEqual(horse["content_version"], changed_horse["content_version"])

        changed = self.horse()
        changed["questions"][0]["answers"][0]["text"] += "!"
        changed["questions"][0]["explanation"] += " Изменено"
        self.write_quiz(changed)
        _, changed_quizzes = self.load()
        changed_horse = next(quiz for quiz in changed_quizzes if quiz["slug"] == "horse-colors")
        self.assertNotEqual(horse["content_version"], changed_horse["content_version"])

    def test_build_does_not_modify_source_and_writes_normalized_quiz(self):
        source = ROOT / "data" / "quizzes" / "horse-colors.json"
        before = source.read_bytes()
        output = self.base / "site"
        catalog = build_site.build(output)
        self.assertEqual(source.read_bytes(), before)
        built = json.loads((output / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        source_quiz = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(len(built["questions"]), len(source_quiz["questions"]))
        self.assertEqual(catalog["quizzes"][0]["question_count"], len(source_quiz["questions"]))
        self.assertEqual(catalog["quizzes"][0]["difficulty"], "low")
        catalog_horse = next(quiz for quiz in catalog["quizzes"] if quiz["slug"] == "horse-colors")
        self.assertEqual(catalog_horse["content_version"], built["content_version"])
        self.assertEqual(
            [question["id"] for question in built["questions"]],
            [question["id"] for question in source_quiz["questions"]],
        )
        self.assertEqual(
            [[answer["id"] for answer in question["answers"]] for question in built["questions"]],
            [[answer["id"] for answer in question["answers"]] for question in source_quiz["questions"]],
        )
        self.assertEqual(sorted(path.name for path in (output / "img" / "quiz" / "horse-colors").iterdir()), [f"{index:02d}.webp" for index in range(1, len(source_quiz["questions"]) + 1)])

    def test_unknown_tag(self):
        self.assert_quiz_error(lambda quiz: quiz.update(tags=["missing-tag"]), "неизвестный тег")

    def test_next_quiz_reference_is_optional_and_validated(self):
        quiz = self.horse()
        quiz["next_quiz"] = "horse-genetics"
        self.write_quiz(quiz)
        _, quizzes = self.load()
        self.assertEqual(next(item for item in quizzes if item["slug"] == "horse-colors")["next_quiz"], "horse-genetics")

        quiz["next_quiz"] = "missing-quiz"
        self.write_quiz(quiz)
        with self.assertRaisesRegex(build_site.ContentError, "next_quiz: неизвестная викторина"):
            self.load()

    def test_published_quiz_cannot_link_to_draft(self):
        target = json.loads((self.data / "quizzes" / "horse-genetics.json").read_text(encoding="utf-8"))
        target["published"] = False
        self.write_quiz(target, "horse-genetics.json")
        quiz = self.horse()
        quiz["next_quiz"] = "horse-genetics"
        self.write_quiz(quiz)
        with self.assertRaisesRegex(build_site.ContentError, "не может ссылаться на неопубликованную"):
            self.load()

    def test_difficulty_is_required_and_restricted(self):
        self.assert_quiz_error(lambda quiz: quiz.pop("difficulty"), "difficulty: требуется одно из значений")
        self.assert_quiz_error(lambda quiz: quiz.update(difficulty="expert"), "difficulty: требуется одно из значений")

    def test_missing_image(self):
        self.assert_quiz_error(lambda quiz: quiz["questions"][0].update(image="img/quiz/missing.webp"), "файл не найден")

    def test_legacy_image_alt_is_removed_from_published_quiz(self):
        quiz = self.horse()
        quiz["questions"][0]["image_alt"] = "Старый индивидуальный alt"
        self.write_quiz(quiz)
        _, quizzes = self.load()
        horse = next(item for item in quizzes if item["slug"] == "horse-colors")
        self.assertNotIn("image_alt", horse["questions"][0])

    def test_question_images_alt_is_optional_and_must_be_a_string(self):
        quiz = self.horse()
        quiz["questionImagesAlt"] = "Фотография лошади для определения масти"
        self.write_quiz(quiz)
        _, quizzes = self.load()
        horse = next(item for item in quizzes if item["slug"] == "horse-colors")
        self.assertEqual(horse["questionImagesAlt"], quiz["questionImagesAlt"])
        self.assert_quiz_error(
            lambda source: source.update(questionImagesAlt=None),
            "questionImagesAlt:",
        )

    def test_build_publishes_every_question_and_image(self):
        source = self.horse()
        expected_count = len(source["questions"])
        output = self.base / "complete-question-site"
        catalog = build_site.build(output)
        horse = next(item for item in catalog["quizzes"] if item["slug"] == "horse-colors")
        published = json.loads((output / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        self.assertEqual(horse["question_count"], expected_count)
        self.assertEqual(len(published["questions"]), expected_count)
        self.assertEqual(
            sorted(path.name for path in (output / "img" / "quiz" / "horse-colors").iterdir()),
            [f"{index:02d}.webp" for index in range(1, expected_count + 1)],
        )

    def test_quiz_filenames_match_their_slugs(self):
        for path in (ROOT / "data" / "quizzes").glob("*.json"):
            quiz = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.stem, quiz["slug"])

    def test_question_images_are_isolated_by_quiz_slug(self):
        _, quizzes = self.load()
        horse = next(quiz for quiz in quizzes if quiz["slug"] == "horse-colors")
        self.assertTrue(all(question["image"].startswith("img/quiz/horse-colors/") for question in horse["questions"]))

        other = self.horse()
        other["slug"] = "other-quiz"
        normalized = build_site.normalize_quiz(other)
        self.assertTrue(all(question["image"].startswith("img/quiz/other-quiz/") for question in normalized["questions"]))
        self.assertEqual(normalized["questions"][0]["image"], "img/quiz/other-quiz/01.webp")

    def test_rejects_image_folder_owned_by_another_quiz(self):
        quiz = self.horse()
        quiz["slug"] = "other-quiz"
        self.write_quiz(quiz, "other-quiz.json")
        tags, known = build_site.load_tags(self.data)
        with self.assertRaisesRegex(build_site.ContentError, "папка изображения должна совпадать"):
            build_site.load_quizzes(self.data, known)


if __name__ == "__main__":
    unittest.main(verbosity=2)
