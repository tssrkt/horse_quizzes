import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VocabularyCmsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        cls.regular = cls.schema.split("  - name: quizzes\n", 1)[1].split("  - name: vocabulary_quizzes\n", 1)[0]
        cls.vocabulary = cls.schema.split("  - name: vocabulary_quizzes\n", 1)[1]

    def test_has_independent_vocabulary_collection(self):
        self.assertIn("label: Викторины", self.regular)
        self.assertIn("label: Словарные викторины", self.vocabulary)
        self.assertIn("path: data/vocabulary-quizzes", self.vocabulary)
        self.assertIn('template: "{fields.slug}.json"', self.vocabulary)

    def test_stores_vocabulary_type_and_repeatable_parts(self):
        self.assertRegex(self.vocabulary, r"name: type\s+type: string\s+hidden: true\s+required: true\s+default: vocabulary")
        parts = self.vocabulary.split("      - name: parts\n", 1)[1]
        self.assertIn("type: object", parts)
        self.assertIn("min: 1", parts)
        self.assertRegex(parts, r"name: id\s+type: uuid\s+required: true")
        self.assertIn("editable: false", parts)
        self.assertIn("name: title", parts)
        table = parts.split("          - name: table\n", 1)[1]
        self.assertIn("type: file", table)
        self.assertIn("required: true", table)
        self.assertIn("media: vocabulary_files", table)
        self.assertIn("extensions: [xlsx, csv]", table)
        media = self.schema.split("  - name: vocabulary_files\n", 1)[1].split("\ncontent:", 1)[0]
        self.assertIn("input: data/vocabulary", media)
        self.assertIn("output: ../vocabulary", media)
        self.assertIn("categories: [spreadsheet]", media)
        self.assertIn("rename: false", media)
        self.assertIn("rename: false", table)
        self.assertNotIn("categories: [spreadsheet]", table)

    def test_upload_fields_preserve_complex_names_in_storage_and_content(self):
        covers_media = self.schema.split("  - name: covers\n", 1)[1].split("  - name: quiz_images\n", 1)[0]
        quiz_media = self.schema.split("  - name: quiz_images\n", 1)[1].split("  - name: vocabulary_files\n", 1)[0]
        self.assertIn("input: img/covers", covers_media)
        self.assertIn("output: img/covers", covers_media)
        self.assertIn("rename: false", covers_media)
        self.assertIn("input: img/quiz", quiz_media)
        self.assertIn("output: img/quiz", quiz_media)
        self.assertIn("rename: false", quiz_media)

        regular_cover = self.regular.split("      - name: cover\n", 1)[1].split("      - name: questionImagesAlt\n", 1)[0]
        question_image = self.regular.split("          - name: image\n", 1)[1].split("          - name: answers\n", 1)[0]
        vocabulary_cover = self.vocabulary.split("      - name: cover\n", 1)[1].split("      - name: tags\n", 1)[0]
        for field in (regular_cover, question_image, vocabulary_cover):
            self.assertIn("rename: false", field)

        # A vocabulary cover must use the exact same upload field contract as a
        # regular quiz cover.  In particular, `type: image` plus the named
        # `covers` media source makes Pages CMS upload the file to `input` and
        # write the source's `output` path to JSON.
        self.assertEqual(regular_cover, vocabulary_cover)

    def test_has_common_fields_but_no_question_editor(self):
        for name in ("title", "slug", "published", "publication_date", "difficulty", "short_description", "intro", "cover", "tags", "next_quiz"):
            self.assertIn(f"- name: {name}", self.vocabulary)
        for forbidden in ("name: questions", "name: answers", "name: questionImagesAlt", "name: image_source"):
            self.assertNotIn(forbidden, self.vocabulary)
        self.assertIn("name: questions", self.regular)

    def test_related_quiz_references_use_separate_collections(self):
        regular_reference = self.regular.split("      - name: next_quiz\n", 1)[1].split("      - name: questions\n", 1)[0]
        vocabulary_reference = self.vocabulary.split("      - name: next_quiz\n", 1)[1].split("      - name: parts\n", 1)[0]

        self.assertIn("path: data/quizzes", self.regular)
        self.assertIn("path: data/vocabulary-quizzes", self.vocabulary)
        self.assertIn("collection: quizzes", regular_reference)
        self.assertNotIn("collection: vocabulary_quizzes", regular_reference)
        self.assertIn("collection: vocabulary_quizzes", vocabulary_reference)
        self.assertNotIn("collection: quizzes\n", vocabulary_reference)
        for reference in (regular_reference, vocabulary_reference):
            self.assertIn("required: false", reference)
            self.assertIn('value: "{fields.slug}"', reference)
            self.assertIn('label: "{fields.title}"', reference)


if __name__ == "__main__":
    unittest.main()
