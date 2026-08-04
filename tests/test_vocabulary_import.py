import csv
import tempfile
import unittest
from pathlib import Path

from tools.build_site import ContentError, import_vocabulary_table


FIXTURE = Path(__file__).parent / "fixtures" / "vocabulary" / "test-english.csv"


class VocabularyImportTests(unittest.TestCase):
    def test_imports_test_fixture(self):
        words = import_vocabulary_table(FIXTURE)
        self.assertEqual(len(words), 4)
        self.assertEqual(words[0]["english"], "gray (grey)")

    def write(self, rows):
        directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        path = Path(directory.name) / "words.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(rows)
        self.addCleanup(directory.cleanup)
        return path

    def test_trims_ignores_empty_and_preserves_synonyms(self):
        path = self.write([["English", "Russian", "Category"], [" gray (grey) ", " серый ", " colors "], ["black", "чёрный", "colors"], ["", "", ""]])
        words = import_vocabulary_table(path)
        self.assertEqual(words[0], {"english": "gray (grey)", "russian": "серый", "category": "colors"})
        self.assertEqual(len(words), 2)

    def test_validates_headers_cells_and_group_size(self):
        with self.assertRaisesRegex(ContentError, "отсутствуют обязательные столбцы"):
            import_vocabulary_table(self.write([["English"], ["horse"]]))
        with self.assertRaisesRegex(ContentError, "English и Russian обязательны"):
            import_vocabulary_table(self.write([["English", "Russian"], ["horse", ""]]))
        with self.assertRaisesRegex(ContentError, "меньше двух строк"):
            import_vocabulary_table(self.write([["English", "Russian", "Category"], ["horse", "лошадь", "animals"]]))


if __name__ == "__main__":
    unittest.main()
