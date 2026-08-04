import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
MEDIA_WORKFLOW = ROOT / ".github" / "workflows" / "organize-quiz-media.yml"


class PagesWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_for_main_and_can_be_started_manually(self):
        self.assertRegex(self.workflow, r"(?m)^\s+branches:\s*\n\s+- main\s*$")
        self.assertRegex(self.workflow, r"(?m)^\s+workflow_dispatch:\s*$")
        self.assertIn("uses: actions/checkout@v6", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+ref: main\s*$")

    def test_uses_single_branch_publication_mechanism(self):
        self.assertIn("git push --force origin HEAD:gh-pages", self.workflow)
        for forbidden in (
            "actions/configure-pages",
            "actions/upload-pages-artifact",
            "actions/deploy-pages",
        ):
            self.assertNotIn(forbidden, self.workflow)

    def test_build_and_catalog_guards_precede_publish(self):
        ordered_fragments = (
            "python tools/normalize_quiz_ids.py",
            "python tools/build_site.py --check",
            "python tools/build_site.py\n",
            'Path("_site/data/catalog.json")',
            'quiz.get("slug") == "horse-colors"',
            "touch .nojekyll",
            "git push --force origin HEAD:gh-pages",
        )
        positions = [self.workflow.index(fragment) for fragment in ordered_fragments]
        self.assertEqual(positions, sorted(positions))

    def test_permissions_and_bot_identity_are_restricted(self):
        self.assertRegex(self.workflow, r"(?m)^permissions:\s*\n\s+contents: write\s*$")
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', self.workflow)
        self.assertIn('git config user.name "github-actions[bot]"', self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+pages: write\s*$")
        self.assertNotRegex(self.workflow, r"(?m)^\s+id-token: write\s*$")

    def test_stale_runs_cannot_publish(self):
        self.assertRegex(self.workflow, r"concurrency:\s+group: pages-publish\s+cancel-in-progress: true")
        freshness = self.workflow.index("git fetch origin main")
        comparison = self.workflow.index('git rev-parse origin/main')
        condition = self.workflow.index("if: steps.freshness.outputs.current == 'true'")
        push = self.workflow.index("git push --force origin HEAD:gh-pages")
        self.assertLess(freshness, comparison)
        self.assertLess(comparison, condition)
        self.assertLess(condition, push)

    def test_id_normalization_does_not_race_to_update_main(self):
        self.assertIn("python tools/normalize_quiz_ids.py", self.workflow)
        self.assertNotIn('git commit -m "Add missing quiz IDs"', self.workflow)
        self.assertNotIn("git push origin HEAD:main", self.workflow)

    def test_media_follow_up_commit_does_not_normalize_ids(self):
        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python scripts/organize_quiz_media.py", workflow)

    def test_media_follow_up_commit_covers_all_cms_upload_directories(self):
        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        scope = "data/quizzes data/vocabulary-quizzes data/vocabulary img/covers img/quiz"
        self.assertIn(f"git diff --quiet -- {scope}", workflow)
        self.assertIn(f"git add -A {scope}", workflow)
        self.assertNotIn("python tools/normalize_quiz_ids.py", workflow)
        self.assertIn("python tools/normalize_quiz_ids.py", self.workflow)

    def test_media_workflow_dispatches_final_build_after_json_and_files_are_aligned(self):
        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(workflow, r"permissions:\s+contents: write\s+actions: write")
        self.assertEqual(workflow.count("gh workflow run pages.yml --ref main"), 2)
        no_change = workflow.index('echo "Quiz media is already organized."')
        no_change_dispatch = workflow.index("gh workflow run pages.yml --ref main", no_change)
        push = workflow.index("git push origin HEAD:main")
        changed_dispatch = workflow.index("gh workflow run pages.yml --ref main", push)
        self.assertLess(no_change, no_change_dispatch)
        self.assertLess(push, changed_dispatch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
