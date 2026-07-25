import html
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts import generate_share_pages


ROOT = Path(__file__).resolve().parents[1]


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.canonical = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name") or attrs.get("http-equiv")
            if key:
                self.meta[key] = attrs.get("content")
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        elif tag == "a":
            self.links.append(attrs.get("href"))


class SharePageTests(unittest.TestCase):
    def test_committed_pages_match_every_published_quiz(self):
        quizzes = generate_share_pages.load_published_quizzes(ROOT)
        expected = {quiz["slug"] for quiz in quizzes}
        actual = {path.parent.name for path in (ROOT / "v").glob("*/index.html")}
        self.assertEqual(actual, expected)
        for quiz in quizzes:
            slug = quiz["slug"]
            source = (ROOT / "v" / slug / "index.html").read_text(encoding="utf-8")
            parser = MetadataParser()
            parser.feed(source)
            direct = f"https://tssrkt.github.io/quiz/quiz.html?quiz={slug}"
            self.assertEqual(parser.meta["og:title"], quiz["title"].strip())
            self.assertEqual(parser.meta["og:description"], quiz["short_description"].strip())
            self.assertTrue(parser.meta["og:image"].startswith("https://"))
            self.assertEqual(parser.meta["og:url"], f"https://tssrkt.github.io/quiz/v/{slug}/")
            self.assertEqual(parser.canonical, direct)
            self.assertEqual(parser.meta["refresh"], f"0; url={direct}")
            self.assertIn(f"window.location.replace({json.dumps(direct, ensure_ascii=False)})", source)
            self.assertIn(direct, parser.links)

    def test_render_escapes_metadata_and_visible_text(self):
        quiz = {
            "slug": "special-test",
            "title": 'Лошади & "пони" <тест>',
            "short_description": 'Описание & "кавычки" <тег>',
            "cover": "img/covers/special test.webp",
        }
        source = generate_share_pages.render_page(quiz)
        self.assertIn("Лошади &amp; &quot;пони&quot; &lt;тест&gt;", source)
        self.assertIn("Описание &amp; &quot;кавычки&quot; &lt;тег&gt;", source)
        self.assertNotIn("<тест>", source)
        parser = MetadataParser()
        parser.feed(source)
        self.assertEqual(parser.meta["og:title"], html.unescape(quiz["title"]))
        self.assertEqual(parser.meta["og:description"], quiz["short_description"])
        self.assertEqual(parser.meta["og:image"], "https://tssrkt.github.io/quiz/img/covers/special%20test.webp")

    def test_generation_removes_stale_page(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "v"
            stale = output / "deleted-quiz"
            stale.mkdir(parents=True)
            (stale / "index.html").write_text("stale", encoding="utf-8")
            count = generate_share_pages.generate(ROOT, output)
            self.assertEqual(count, len(generate_share_pages.load_published_quizzes(ROOT)))
            self.assertFalse(stale.exists())

    def test_sharing_changed_without_rewriting_internal_navigation(self):
        quiz_js = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        catalog_js = (ROOT / "js" / "quizzes.js").read_text(encoding="utf-8")
        self.assertIn("core.shareQuizUrl(quiz.slug)", quiz_js)
        self.assertIn("quiz.html?quiz=${encodeURIComponent(nextQuiz.slug)}", quiz_js)
        self.assertIn("quiz.html?quiz=${encodeURIComponent(quiz.slug)}", catalog_js)


if __name__ == "__main__":
    unittest.main()
