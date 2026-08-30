import html
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts import generate_share_pages
from scripts.site_config import load_site_config


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_URL = load_site_config(ROOT)["public_url"]


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
    def test_generated_pages_match_every_published_quiz(self):
        quizzes = generate_share_pages.load_published_quizzes(ROOT)
        russian_quizzes = [quiz for quiz in quizzes if quiz.get("type") != "english"]
        english_quizzes = [quiz for quiz in quizzes if quiz.get("type") == "english"]
        expected = {quiz["slug"] for quiz in russian_quizzes}
        expected_english = {quiz["source_quiz"] for quiz in english_quizzes}
        self.assertEqual(len(expected_english), len(english_quizzes), "duplicate source_quiz")
        russian_by_slug = {quiz["slug"]: quiz for quiz in russian_quizzes}
        self.assertTrue(expected_english.issubset(russian_by_slug), "English quiz without a Russian source")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "v"
            english_output = Path(directory) / "en/v"
            generate_share_pages.generate(ROOT, output, english_output)
            actual = {path.parent.name for path in output.glob("*/index.html")}
            self.assertEqual(actual, expected)
            self.assertEqual({path.parent.name for path in english_output.glob("*/index.html")}, expected_english)
            for quiz in russian_quizzes:
                slug = quiz["slug"]
                source = (output / slug / "index.html").read_text(encoding="utf-8")
                parser = MetadataParser()
                parser.feed(source)
                share_url = f"{PUBLIC_URL}v/{slug}/"
                self.assertEqual(parser.meta["og:title"], quiz["title"].strip())
                self.assertEqual(parser.meta["og:description"], quiz["short_description"].strip())
                self.assertTrue(parser.meta["og:image"].startswith("https://"))
                self.assertEqual(parser.meta["og:url"], share_url)
                self.assertEqual(parser.canonical, share_url)
                self.assertNotIn("robots", parser.meta)
                self.assertNotIn("refresh", parser.meta)
                self.assertNotIn("location.replace", source)
                self.assertIn('id="quiz-app"', source)
                self.assertIn('src="../../js/quiz.js"', source)
                self.assertIn('src="../../js/site-config.js"', source)
                self.assertIn('src="../../js/urls.js"', source)
                self.assertIn('href="../../css/style.css"', source)
                self.assertNotRegex(source, r'(?:href|src)="(?:css|js|img)/')
            for quiz in english_quizzes:
                source_slug = quiz["source_quiz"]
                self.assertFalse((output / quiz["slug"] / "index.html").exists())
                english_page = english_output / source_slug / "index.html"
                self.assertTrue(english_page.is_file())
                english_source = english_page.read_text(encoding="utf-8")
                parser = MetadataParser()
                parser.feed(english_source)
                self.assertEqual(parser.canonical, f"{PUBLIC_URL}en/v/{source_slug}/")
                self.assertIn(f'../../../v/{source_slug}/', parser.links)
                russian_source = (output / source_slug / "index.html").read_text(encoding="utf-8")
                self.assertIn(f'../../en/v/{source_slug}/', russian_source)
                self.assertNotIn(f'/v/{quiz["slug"]}/', english_source)

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
        self.assertEqual(parser.meta["og:image"], f"{PUBLIC_URL}img/covers/special%20test.webp")

    def test_generation_removes_stale_page(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "v"
            stale = output / "deleted-quiz"
            stale.mkdir(parents=True)
            (stale / "index.html").write_text("stale", encoding="utf-8")
            count = generate_share_pages.generate(ROOT, output)
            self.assertEqual(count, len(generate_share_pages.load_published_quizzes(ROOT)))
            self.assertFalse(stale.exists())

    def test_vocabulary_pages_use_section_specific_seo_title(self):
        quizzes = generate_share_pages.load_published_quizzes(ROOT)
        vocabulary = next(quiz for quiz in quizzes if quiz["slug"] == "english")
        ordinary = next(quiz for quiz in quizzes if quiz["slug"] == "horse-exterior")
        vocabulary_page = generate_share_pages.render_page(vocabulary)
        ordinary_page = generate_share_pages.render_page(ordinary)
        self.assertIn("<title>Экстерьер лошади — Английский для конников</title>", vocabulary_page)
        self.assertIn("<title>Экстерьер лошади — Викторины о лошадках</title>", ordinary_page)
        self.assertNotEqual(
            vocabulary_page.split("<title>", 1)[1].split("</title>", 1)[0],
            ordinary_page.split("<title>", 1)[1].split("</title>", 1)[0],
        )
        self.assertIn('<meta property="og:site_name" content="Викторины о лошадках">', vocabulary_page)

    def test_sharing_changed_without_rewriting_internal_navigation(self):
        quiz_js = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        catalog_js = (ROOT / "js" / "quizzes.js").read_text(encoding="utf-8")
        self.assertIn("englishSite ? quiz.source_quiz : quiz.slug", quiz_js)
        self.assertIn("nextQuiz.public_slug || nextQuiz.slug", quiz_js)
        self.assertIn("quiz.public_slug || quiz.slug", catalog_js)
        self.assertNotIn("quiz.html?quiz=${encodeURIComponent(quiz.slug)}", catalog_js)

    def test_catalog_intro_uses_relative_share_urls(self):
        source = (ROOT / "quizzes.html").read_text(encoding="utf-8")
        expected = {
            "Породы лошадей": "v/horse-breeds/",
            "Масти лошадей": "v/horse-colors/",
            "Лошадиные термины": "v/horse-words/",
            "Генетику лошади": "v/horse-genetics/",
        }
        for label, url in expected.items():
            self.assertIn(f'href="{url}"', source)
            self.assertIn(label, source)
        self.assertNotIn("quiz.html?quiz=", source)


if __name__ == "__main__":
    unittest.main()
