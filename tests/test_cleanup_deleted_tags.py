import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.cleanup_deleted_tags import cleanup


class CleanupDeletedTagsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for directory in ("data/quizzes", "data/vocabulary-quizzes"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, directory, name, tags):
        path = self.root / directory / f"{name}.json"
        path.write_text(json.dumps({"slug": name, "tags": tags}, ensure_ascii=False), encoding="utf-8")
        return path

    def read_tags(self, path):
        return json.loads(path.read_text(encoding="utf-8"))["tags"]

    def test_removes_only_selected_tag_from_both_quiz_types(self):
        regular = self.write("data/quizzes", "regular", ["remove-me", "keep-me"])
        vocabulary = self.write("data/vocabulary-quizzes", "vocabulary", ["keep-me", "remove-me"])
        emptied = self.write("data/quizzes", "empty", ["remove-me"])
        changed = cleanup(self.root, {"remove-me"})
        self.assertEqual(set(changed), {regular, vocabulary, emptied})
        self.assertEqual(self.read_tags(regular), ["keep-me"])
        self.assertEqual(self.read_tags(vocabulary), ["keep-me"])
        self.assertEqual(self.read_tags(emptied), [])

    def test_unused_tag_does_not_modify_quizzes(self):
        quiz = self.write("data/quizzes", "regular", ["keep-me"])
        before = quiz.read_bytes()
        self.assertEqual(cleanup(self.root, {"unused"}), [])
        self.assertEqual(quiz.read_bytes(), before)

    def test_invalid_related_quiz_prevents_all_updates(self):
        first = self.write("data/quizzes", "regular", ["remove-me", "keep-me"])
        broken = self.root / "data/vocabulary-quizzes/broken.json"
        broken.write_text("{broken", encoding="utf-8")
        before = first.read_bytes()
        with self.assertRaises(json.JSONDecodeError):
            cleanup(self.root, {"remove-me"})
        self.assertEqual(first.read_bytes(), before)

    def test_write_failure_rolls_back_already_replaced_quizzes(self):
        first = self.write("data/quizzes", "first", ["remove-me"])
        second = self.write("data/quizzes", "second", ["remove-me", "keep-me"])
        before = {path: path.read_bytes() for path in (first, second)}
        original_replace = Path.replace
        calls = 0

        def fail_second(path, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("write failed")
            return original_replace(path, target)

        with patch.object(Path, "replace", fail_second), self.assertRaises(OSError):
            cleanup(self.root, {"remove-me"})
        self.assertEqual(first.read_bytes(), before[first])
        self.assertEqual(second.read_bytes(), before[second])


if __name__ == "__main__":
    unittest.main()
