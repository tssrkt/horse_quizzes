import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.normalize_quiz_ids import IdNormalizationError, normalize_file, normalize_quiz_ids


ROOT = Path(__file__).resolve().parents[1]


def answer(answer_id, text="Ответ"):
    value = {"text": text, "correct": False}
    if answer_id is not None:
        value["id"] = answer_id
    return value


def question(question_id, answers=None, text="Вопрос"):
    value = {"question": text, "answers": answers or [answer("answer-01"), answer("answer-02")]}
    if question_id is not None:
        value["id"] = question_id
    return value


class NormalizeQuizIdsTests(unittest.TestCase):
    def test_vocabulary_without_questions_is_accepted_unchanged(self):
        quiz = {"type": "vocabulary", "table": "../vocabulary/words.xlsx"}
        original = copy.deepcopy(quiz)
        self.assertFalse(normalize_quiz_ids(quiz, "vocabulary.json"))
        self.assertEqual(quiz, original)

        with tempfile.TemporaryDirectory(prefix=".id-test-", dir=ROOT) as directory:
            path = Path(directory) / "vocabulary.json"
            path.write_text(json.dumps(quiz, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            self.assertFalse(normalize_file(path))
            self.assertEqual(path.read_bytes(), before)

    def test_regular_quiz_without_questions_remains_invalid(self):
        with self.assertRaisesRegex(IdNormalizationError, "questions"):
            normalize_quiz_ids({"type": "quiz"}, "regular.json")

    def test_assigns_after_maximum_without_reusing_gaps(self):
        quiz = {"questions": [question("question-01"), question("question-02"), question("question-05"), question(None)]}
        self.assertTrue(normalize_quiz_ids(quiz))
        self.assertEqual([item["id"] for item in quiz["questions"]], ["question-01", "question-02", "question-05", "question-06"])

        answers = [answer("answer-01"), answer("answer-02"), answer("answer-04"), answer("  ")]
        quiz = {"questions": [question("question-01", answers)]}
        normalize_quiz_ids(quiz)
        self.assertEqual([item["id"] for item in answers], ["answer-01", "answer-02", "answer-04", "answer-05"])

    def test_numbers_above_99(self):
        quiz = {"questions": [question("question-99"), question(None, [answer("answer-99"), answer(None)])]}
        normalize_quiz_ids(quiz)
        self.assertEqual(quiz["questions"][1]["id"], "question-100")
        self.assertEqual(quiz["questions"][1]["answers"][1]["id"], "answer-100")

    def test_tenth_question_and_its_answers_receive_expected_ids(self):
        questions = [question(f"question-{index:02d}") for index in range(1, 10)]
        questions.append(question(None, [answer(None) for _ in range(4)]))
        quiz = {"questions": questions}
        self.assertTrue(normalize_quiz_ids(quiz))
        self.assertEqual(quiz["questions"][9]["id"], "question-10")
        self.assertEqual(
            [item["id"] for item in quiz["questions"][9]["answers"]],
            ["answer-01", "answer-02", "answer-03", "answer-04"],
        )

    def test_existing_ids_survive_edits_reordering_and_deletion(self):
        original = {"questions": [question("question-02"), question("question-05")]}
        changed = copy.deepcopy(original)
        changed["questions"][1]["question"] = "Новый текст"
        changed["questions"][1]["answers"][1]["text"] = "Новый ответ"
        changed["questions"].reverse()
        changed["questions"][0]["answers"].reverse()
        changed["questions"].pop()
        self.assertFalse(normalize_quiz_ids(changed))
        self.assertEqual(changed["questions"][0]["id"], "question-05")
        self.assertEqual([item["id"] for item in changed["questions"][0]["answers"]], ["answer-02", "answer-01"])

    def test_duplicate_question_and_answer_ids_are_reported(self):
        with self.assertRaisesRegex(IdNormalizationError, "конфликтующий ID «question-01».*1 и 2"):
            normalize_quiz_ids({"questions": [question("question-01"), question("question-01")]}, "quiz.json")
        duplicate_answers = [answer("answer-01"), answer("answer-01")]
        with self.assertRaisesRegex(IdNormalizationError, "конфликтующий ID «answer-01».*1 и 2"):
            normalize_quiz_ids({"questions": [question("question-01", duplicate_answers)]}, "quiz.json")

    def test_file_normalization_is_idempotent(self):
        with tempfile.TemporaryDirectory(prefix=".id-test-", dir=ROOT) as directory:
            path = Path(directory) / "quiz.json"
            path.write_text(json.dumps({"questions": [question(None, [answer(None), answer("")])]}, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(normalize_file(path))
            first = path.read_bytes()
            self.assertFalse(normalize_file(path))
            self.assertEqual(path.read_bytes(), first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
