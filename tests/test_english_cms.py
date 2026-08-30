import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EnglishCmsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        cls.prepare_workflow = (ROOT / ".github/workflows/translate-english-quiz.yml").read_text(encoding="utf-8")
        cls.import_workflow = (ROOT / ".github/workflows/import-english-translation.yml").read_text(encoding="utf-8")
        cls.script = (ROOT / "scripts/sync_english_quiz.py").read_text(encoding="utf-8")
        cls.import_script = (ROOT / "scripts/import_english_translation.py").read_text(encoding="utf-8")

    def test_regular_quiz_has_translation_action(self):
        regular = self.config.split("  - name: quizzes\n", 1)[1].split("  - name: english_quizzes\n", 1)[0]
        self.assertIn("label: Подготовить английскую версию", regular)
        self.assertIn("workflow: translate-english-quiz.yml", regular)
        self.assertIn("scope: entry", regular)

    def test_english_collection_is_separate_and_not_manually_created(self):
        english = self.config.split("  - name: english_quizzes\n", 1)[1].split("  - name: vocabulary_quizzes\n", 1)[0]
        self.assertIn("path: data/english-quizzes", english)
        operations = english.split("    operations:\n", 1)[1].split("    filename:\n", 1)[0]
        self.assertIn("create: false", operations)
        self.assertNotIn("delete: false", operations)
        self.assertIn("default: english", english)
        self.assertIn("collection: quizzes", english)
        self.assertIn("translation_status", english)
        self.assertIn("primary: title", english)
        self.assertIn("sort: [title]", english)
        self.assertIn('label: "{fields.title}"', english)
        self.assertEqual(english.count("collection: english_quizzes"), 0)

    def test_prepare_workflow_stages_untracked_files_before_diff_check(self):
        workflow = self.prepare_workflow
        add = workflow.index("git add -A data/quizzes data/english-quizzes data/translation-packages")
        check = workflow.index("git diff --cached --quiet")
        commit = workflow.index('git commit -m "Prepare English translation package"')
        self.assertLess(add, check)
        self.assertLess(check, commit)
        self.assertNotIn("git diff --quiet -- data/quizzes data/english-quizzes data/translation-packages", workflow)

    def test_translation_packages_have_separate_import_action(self):
        packages = self.config.split("  - name: translation_packages\n", 1)[1]
        self.assertIn("path: data/translation-packages", packages)
        self.assertIn("subfolders: false", packages)
        self.assertIn('exclude: ["imported/**"]', packages)
        self.assertIn("create: false", packages)
        self.assertIn("label: Импортировать перевод", packages)
        self.assertIn("workflow: import-english-translation.yml", packages)
        self.assertIn("scope: entry", packages)

    def test_workflows_need_no_openai_api_and_write_summaries(self):
        combined = "\n".join((self.config, self.prepare_workflow, self.import_workflow, self.script, self.import_script))
        self.assertNotIn("OPENAI_API_KEY", combined)
        self.assertNotIn("OPENAI_TRANSLATION_MODEL", combined)
        self.assertNotIn("api.openai.com", combined)
        self.assertIn('--summary "$GITHUB_STEP_SUMMARY"', self.prepare_workflow)
        self.assertIn('--summary "$GITHUB_STEP_SUMMARY"', self.import_workflow)
        self.assertIn("python tools/build_site.py --check", self.prepare_workflow)
        self.assertIn("python tools/build_site.py --check", self.import_workflow)
        self.assertIn("Previous package path", self.import_script)
        self.assertIn("Archived package path", self.import_script)
        self.assertIn("Partial changes", self.import_script)

    def test_translation_instructions_protect_structure_and_terminology(self):
        for phrase in ("equestrian", "veterinary", "genetic", "Do not change JSON keys", "IDs", "structure", "order", "tags"):
            self.assertIn(phrase, self.script)


if __name__ == "__main__":
    unittest.main()
