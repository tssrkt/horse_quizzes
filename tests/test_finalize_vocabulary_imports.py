import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.finalize_vocabulary_imports import finalize
from tools import build_site


class FinalizeVocabularyImportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data" / "vocabulary-quizzes").mkdir(parents=True)
        (self.root / "data" / "vocabulary").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_quiz(self, table):
        path = self.root / "data" / "vocabulary-quizzes" / "test.json"
        data = {"type": "vocabulary", "slug": "test", "parts": [{"id": "part-1", "table": f"../vocabulary/{table}"}]}
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def xlsx(self, name="words.xlsx"):
        path = self.root / "data" / "vocabulary" / name
        rows = '<row r="1"><c r="A1" t="inlineStr"><is><t>English</t></is></c><c r="B1" t="inlineStr"><is><t>Russian</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>horse</t></is></c><c r="B2" t="inlineStr"><is><t>лошадь</t></is></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>mare</t></is></c><c r="B3" t="inlineStr"><is><t>кобыла</t></is></c></row>'
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Words" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>')
        return path

    def assert_successful_import(self, table_path):
        json_path = self.write_quiz(table_path.name)
        with patch.object(build_site, "ROOT", self.root):
            self.assertEqual(finalize(self.root), (1, 1))
        self.assertFalse(table_path.exists())
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual([word["english"] for word in saved["parts"][0]["vocabulary"]], ["horse", "mare"])

    def test_xlsx_is_removed_after_json_is_saved(self):
        self.assert_successful_import(self.xlsx())

    def test_csv_is_removed_after_json_is_saved(self):
        path = self.root / "data" / "vocabulary" / "words.csv"
        path.write_text("English,Russian,Category\nhorse,лошадь,\nmare,кобыла,\n", encoding="utf-8")
        self.assert_successful_import(path)

    def test_failed_import_keeps_table_and_json_unchanged(self):
        path = self.root / "data" / "vocabulary" / "broken.csv"
        path.write_text("English,Russian\nhorse,\n", encoding="utf-8")
        json_path = self.write_quiz(path.name)
        before = json_path.read_bytes()
        with patch.object(build_site, "ROOT", self.root), self.assertRaises(build_site.ContentError):
            finalize(self.root)
        self.assertTrue(path.exists())
        self.assertEqual(json_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
