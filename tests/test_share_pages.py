import html
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
            share_url = f"https://tssrkt.github.io/quiz/v/{slug}/"
            self.assertEqual(parser.meta["og:title"], quiz["title"].strip())
            self.assertEqual(parser.meta["og:description"], quiz["short_description"].strip())
            self.assertTrue(parser.meta["og:image"].startswith("https://"))
            self.assertEqual(parser.meta["og:url"], share_url)
            self.assertEqual(parser.canonical, share_url)
            self.assertNotIn("refresh", parser.meta)
            self.assertNotIn("location.replace", source)
            self.assertIn('id="quiz-app"', source)
            self.assertIn('src="../../js/quiz.js"', source)
            self.assertIn('src="../../js/urls.js"', source)
            self.assertIn('href="../../css/style.css"', source)
            self.assertNotRegex(source, r'(?:href|src)="(?:css|js|img)/')

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
        self.assertIn("core.quizPath(nextQuiz.slug, location.href)", quiz_js)
        self.assertIn("urlCore.quizPath(quiz.slug, location.href)", catalog_js)
        self.assertNotIn("quiz.html?quiz=${encodeURIComponent(quiz.slug)}", catalog_js)

    def test_catalog_intro_uses_full_share_urls(self):
        source = (ROOT / "quizzes.html").read_text(encoding="utf-8")
        expected = {
            "Породы лошадей": "https://tssrkt.github.io/quiz/v/horse-breeds/",
            "Масти лошадей": "https://tssrkt.github.io/quiz/v/horse-colors/",
            "Лошадиная терминология": "https://tssrkt.github.io/quiz/v/horse-words/",
            "Генетику лошади": "https://tssrkt.github.io/quiz/v/horse-genetics/",
        }
        for label, url in expected.items():
            self.assertIn(f'href="{url}"', source)
            self.assertIn(label, source)
        self.assertNotIn("quiz.html?quiz=", source)


if __name__ == "__main__":
    unittest.main()
