import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EnglishCmsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github/workflows/translate-english-quiz.yml").read_text(encoding="utf-8")
        cls.script = (ROOT / "scripts/sync_english_quiz.py").read_text(encoding="utf-8")

    def test_regular_quiz_has_translation_action(self):
        regular = self.config.split("  - name: quizzes\n", 1)[1].split("  - name: english_quizzes\n", 1)[0]
        self.assertIn("label: Создать/обновить английскую версию", regular)
        self.assertIn("workflow: translate-english-quiz.yml", regular)
        self.assertIn("scope: entry", regular)

    def test_english_collection_is_separate_and_not_manually_created(self):
        english = self.config.split("  - name: english_quizzes\n", 1)[1].split("  - name: vocabulary_quizzes\n", 1)[0]
        self.assertIn("path: data/english-quizzes", english)
        self.assertIn("create: false", english)
        self.assertIn("default: english", english)
        self.assertIn("collection: quizzes", english)
        self.assertIn("translation_status", english)

    def test_workflow_keeps_api_key_server_side_and_writes_summary(self):
        self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}", self.workflow)
        self.assertIn('OPENAI_TRANSLATION_MODEL: ${{ vars.OPENAI_TRANSLATION_MODEL || \'gpt-5.6-terra\' }}', self.workflow)
        self.assertIn('--summary "$GITHUB_STEP_SUMMARY"', self.workflow)
        self.assertNotIn("OPENAI_API_KEY", self.config)
        self.assertIn("python tools/build_site.py --check", self.workflow)

    def test_translation_prompt_protects_structure_and_domain_terminology(self):
        for phrase in ("equestrian terminology", "veterinary", "genetic", "Do not change correct answers", "item order", "images", "service fields"):
            self.assertIn(phrase, self.script)


if __name__ == "__main__":
    unittest.main()
