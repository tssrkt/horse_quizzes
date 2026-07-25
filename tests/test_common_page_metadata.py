import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from tools import build_site


ROOT = Path(__file__).resolve().parents[1]
IMAGE_URL = "https://tssrkt.github.io/quiz/img/site-preview.webp"
GENERAL_DESCRIPTION = "Познавательные викторины о породах, мастях, генетике, анатомии, уходе за лошадьми и конной терминологии."


class HeadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.canonical = None
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key:
                self.meta[key] = attrs.get("content")
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


PAGES = {
    "index.html": (
        "Викторины о лошадках",
        GENERAL_DESCRIPTION,
        "https://tssrkt.github.io/quiz/",
    ),
    "quizzes.html": (
        "Викторины о лошадках",
        GENERAL_DESCRIPTION,
        "https://tssrkt.github.io/quiz/quizzes.html",
    ),
    "contacts.html": (
        "Викторины о лошадках",
        "Связаться с автором проекта «Викторины о лошадках» и поддержать развитие сайта.",
        "https://tssrkt.github.io/quiz/contacts.html",
    ),
    "404.html": (
        "Страница 404",
        "Страница не найдена.",
        "https://tssrkt.github.io/quiz/404.html",
    ),
}


class CommonPageMetadataTests(unittest.TestCase):
    def parse(self, path):
        parser = HeadParser()
        parser.feed(path.read_text(encoding="utf-8"))
        return parser

    def assert_metadata(self, parser, title, description, canonical):
        self.assertEqual(parser.title, title)
        self.assertEqual(parser.meta["description"], description)
        self.assertEqual(parser.meta["og:type"], "website")
        self.assertEqual(parser.meta["og:site_name"], "Викторины о лошадках")
        self.assertEqual(parser.meta["og:locale"], "ru_RU")
        self.assertEqual(parser.meta["og:title"], title)
        self.assertEqual(parser.meta["og:description"], description)
        self.assertEqual(parser.meta["og:url"], canonical)
        self.assertEqual(parser.meta["og:image"], IMAGE_URL)
        self.assertEqual(parser.meta["og:image:alt"], "Викторины о лошадках")
        self.assertEqual(parser.meta["twitter:card"], "summary")
        self.assertEqual(parser.meta["twitter:title"], title)
        self.assertEqual(parser.meta["twitter:description"], description)
        self.assertEqual(parser.meta["twitter:image"], IMAGE_URL)
        self.assertEqual(parser.canonical, canonical)

    def test_source_pages_have_exact_metadata(self):
        for filename, expected in PAGES.items():
            with self.subTest(filename=filename):
                source = (ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("Русскоязычные викторины на самые разные темы.", source)
                self.assertNotIn("Русскоязыные викторины на самые разные темы.", source)
                self.assert_metadata(self.parse(ROOT / filename), *expected)

    def test_quiz_share_pages_keep_individual_metadata(self):
        anatomy = self.parse(ROOT / "v" / "anatomy" / "index.html")
        self.assertEqual(anatomy.meta["og:title"], "Анатомия лошади")
        self.assertEqual(anatomy.meta["og:image"], "https://tssrkt.github.io/quiz/img/covers/anatomy.webp")
        self.assertNotEqual(anatomy.meta["og:image"], IMAGE_URL)

    def test_build_preserves_html_and_copies_preview_bytes(self):
        with tempfile.TemporaryDirectory(prefix=".metadata-build-", dir=ROOT) as directory:
            output = Path(directory) / "site"
            build_site.build(output)
            self.assertEqual(
                (output / "img" / "site-preview.webp").read_bytes(),
                (ROOT / "img" / "site-preview.webp").read_bytes(),
            )
            for filename, expected in PAGES.items():
                with self.subTest(filename=filename):
                    self.assert_metadata(self.parse(output / filename), *expected)


if __name__ == "__main__":
    unittest.main()
