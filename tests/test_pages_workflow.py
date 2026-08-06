import unittest
import re
from fnmatch import fnmatchcase
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
MEDIA_WORKFLOW = ROOT / ".github" / "workflows" / "organize-quiz-media.yml"


class PagesWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.media_workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")

    @staticmethod
    def _patterns(workflow, key):
        block = workflow.split(f"    {key}:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        return re.findall(r'^\s+- "([^"]+)"\s*$', block, re.MULTILINE)

    @classmethod
    def pages_push_runs_for(cls, *paths):
        ignored = cls._patterns(cls.workflow, "paths-ignore")
        return any(not any(fnmatchcase(path, pattern) for pattern in ignored) for path in paths)

    @classmethod
    def media_push_runs_for(cls, *paths):
        included = cls._patterns(cls.media_workflow, "paths")
        return any(any(fnmatchcase(path, pattern) for pattern in included) for path in paths)

    def test_runs_for_main_and_can_be_started_manually(self):
        self.assertRegex(self.workflow, r"(?m)^\s+branches:\s*\n\s+- main\s*$")
        self.assertRegex(self.workflow, r"(?m)^\s+workflow_dispatch:\s*$")
        self.assertIn("uses: actions/checkout@v6", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+ref: main\s*$")

    def test_cms_managed_pushes_wait_for_finalization(self):
        ignored = (
            "data/quizzes/**",
            "data/vocabulary-quizzes/**",
            "data/english-quizzes/**",
            "data/tags/**",
            "data/vocabulary/**",
            "img/covers/**",
            "img/quiz/**",
        )
        self.assertIn("paths-ignore:", self.workflow)
        for path in ignored:
            self.assertIn(f'- "{path}"', self.workflow)

        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        for saved_content in (
            'data/quizzes/*.json',
            'data/vocabulary-quizzes/*.json',
        ):
            self.assertIn(f'- "{saved_content}"', workflow)

    def test_source_changes_still_trigger_pages_directly(self):
        for path in ("index.html", "css/style.css", "js/quizzes.js", "tools/build_site.py", ".github/workflows/pages.yml"):
            with self.subTest(path=path):
                self.assertTrue(self.pages_push_runs_for(path))

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
        self.assertRegex(self.workflow, r"concurrency:\s+group: pages-publish(?:.|\n)*?cancel-in-progress: false")
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
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn('PREVIOUS_REF: ${{ github.event.before }}', workflow)
        self.assertIn('python scripts/organize_quiz_media.py --previous-ref "${PREVIOUS_REF}"', workflow)
        self.assertIn("python scripts/finalize_vocabulary_imports.py", workflow)
        self.assertLess(workflow.index("python scripts/organize_quiz_media.py"), workflow.index("python scripts/finalize_vocabulary_imports.py"))

    def test_media_follow_up_commit_covers_all_cms_upload_directories(self):
        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        scope = "data/quizzes data/vocabulary-quizzes data/english-quizzes data/tags data/vocabulary img/covers img/quiz"
        self.assertIn('- "data/tags/*.json"', workflow)
        self.assertIn('- "data/vocabulary/*.xlsx"', workflow)
        self.assertIn('- "data/vocabulary/*.csv"', workflow)
        self.assertIn('- "img/covers/*"', workflow)
        self.assertIn('- "img/quiz/**/*"', workflow)
        self.assertNotIn('- "img/quiz/*"', workflow)
        self.assertIn(f"git diff --quiet -- {scope}", workflow)
        self.assertIn(f"git add -A {scope}", workflow)
        self.assertIn('python scripts/cleanup_deleted_tags.py --previous-ref "${PREVIOUS_REF}"', workflow)
        cleanup = workflow.index("python scripts/cleanup_deleted_tags.py")
        validation = workflow.index("python tools/build_site.py --check")
        commit = workflow.index('git commit -m "Organize quiz media"')
        self.assertLess(cleanup, validation)
        self.assertLess(validation, commit)
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

    def test_save_has_only_one_pages_entry_point(self):
        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('- "data/quizzes/*.json"', workflow)
        self.assertIn('- "data/vocabulary-quizzes/*.json"', workflow)
        self.assertIn('- "data/quizzes/**"', self.workflow)
        self.assertIn('- "data/vocabulary-quizzes/**"', self.workflow)
        self.assertEqual(workflow.count("gh workflow run pages.yml --ref main"), 2)
        for path in ("data/quizzes/cms-save.json", "data/vocabulary-quizzes/cms-save.json"):
            with self.subTest(path=path):
                self.assertFalse(self.pages_push_runs_for(path))
                self.assertTrue(self.media_push_runs_for(path))

    def test_existing_quiz_json_only_edit_dispatches_one_final_build(self):
        path = "data/quizzes/horse-colors.json"
        workflow = self.media_workflow

        # A text-only CMS Save is routed to finalization, never directly to
        # Pages, and cannot be mistaken for an added media file.
        self.assertFalse(self.pages_push_runs_for(path))
        self.assertTrue(self.media_push_runs_for(path))
        self.assertNotRegex(path, r"^img/(covers|quiz)/[^/]+$")

        # With no generated diff, the saved JSON is already the final main
        # state. It is dispatched once and the shell exits before the branch
        # that commits generated changes.
        no_diff = workflow.index("if git diff --quiet --")
        no_diff_dispatch = workflow.index("gh workflow run pages.yml --ref main", no_diff)
        no_diff_exit = workflow.index("exit 0", no_diff_dispatch)
        commit = workflow.index('git commit -m "Organize quiz media"')
        self.assertLess(no_diff, no_diff_dispatch)
        self.assertLess(no_diff_dispatch, no_diff_exit)
        self.assertLess(no_diff_exit, commit)

        # The dispatched Pages run checks out that final main revision and
        # rebuilds the published JSON without requiring an empty commit.
        self.assertIn("uses: actions/checkout@v6", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+ref: main\s*$")
        self.assertIn("python tools/build_site.py", self.workflow)
        self.assertNotIn("--allow-empty", workflow)

    def test_raw_uploads_do_not_start_either_workflow(self):
        workflow = MEDIA_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('- "img/quiz/**"', self.workflow)
        self.assertNotIn('- "img/quiz/*"', workflow)
        self.assertIn('- "img/quiz/**/*"', workflow)
        uploads = ("img/quiz/36.webp", "img/quiz/37.webp", "img/quiz/38.webp")
        self.assertFalse(self.pages_push_runs_for(*uploads))
        self.assertFalse(self.media_push_runs_for(*uploads))

    def test_new_cover_upload_is_skipped_but_replacement_is_finalized(self):
        workflow = self.media_workflow
        self.assertIn('git diff --name-status "${PREVIOUS_REF}" "${GITHUB_SHA}"', workflow)
        self.assertIn('"${status}" != "A"', workflow)
        self.assertIn('^img/(covers|quiz)/[^/]+$', workflow)
        skip = workflow.index("Only intermediate Pages CMS image uploads changed")
        dispatch = workflow.index("gh workflow run pages.yml --ref main")
        self.assertLess(skip, dispatch)
        self.assertFalse(self.pages_push_runs_for("img/covers/new-cover.webp"))
        self.assertTrue(self.media_push_runs_for("img/covers/new-cover.webp"))

    def test_published_image_replacement_is_finalized_then_published(self):
        path = "img/quiz/horse-colors/01.webp"
        self.assertFalse(self.pages_push_runs_for(path))
        self.assertTrue(self.media_push_runs_for(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
