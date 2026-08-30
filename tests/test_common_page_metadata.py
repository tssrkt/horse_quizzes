import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from tools import build_site
from scripts.site_config import load_site_config


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_URL = load_site_config(ROOT)["public_url"]
IMAGE_URL = f"{PUBLIC_URL}img/site-preview.webp"
GENERAL_DESCRIPTION = "Познавательные викторины о породах, мастях, генетике, анатомии, уходе за лошадьми и конной терминологии."


class HeadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.meta_counts = {}
        self.alternates = {}
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
                self.meta_counts[key] = self.meta_counts.get(key, 0) + 1
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        elif tag == "link" and attrs.get("rel") == "alternate":
            self.alternates[attrs.get("hreflang")] = attrs.get("href")

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
        PUBLIC_URL,
    ),
    "quizzes.html": (
        "Викторины о лошадках",
        GENERAL_DESCRIPTION,
        f"{PUBLIC_URL}quizzes.html",
    ),
    "contacts.html": (
        "Викторины о лошадках",
        "Связаться с автором проекта «Викторины о лошадках» и поддержать развитие сайта.",
        f"{PUBLIC_URL}contacts.html",
    ),
    "404.html": (
        "Страница 404",
        "Страница не найдена.",
        f"{PUBLIC_URL}404.html",
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

    def assert_english_page_metadata(self, path, title, og_title, description, canonical, russian):
        parser = self.parse(path)
        expected = {
            "description": description,
            "og:type": "website",
            "og:site_name": "Horse Quizzes",
            "og:locale": "en_US",
            "og:locale:alternate": "ru_RU",
            "og:title": og_title,
            "og:description": description,
            "og:url": canonical,
            "og:image": IMAGE_URL,
            "og:image:alt": "Horse Quizzes",
            "twitter:card": "summary",
            "twitter:title": og_title,
            "twitter:description": description,
            "twitter:image": IMAGE_URL,
        }
        self.assertEqual(parser.title, title)
        self.assertEqual(parser.canonical, canonical)
        self.assertEqual(parser.alternates, {"ru": russian, "en": canonical, "x-default": russian})
        for key, value in expected.items():
            self.assertEqual(parser.meta.get(key), value, key)
            self.assertEqual(parser.meta_counts.get(key), 1, f"duplicate metadata: {key}")

    def test_english_catalog_and_contacts_have_complete_unique_metadata(self):
        pages = (
            ("quizzes.html", "Choose a Quiz — Horse Quizzes", "Choose a Quiz", "Browse published horse quizzes in English.", "quizzes.html"),
            ("contacts.html", "Contacts — Horse Quizzes", "Contacts — Horse Quizzes", "Contact the Horse Quizzes project author and support the site.", "contacts.html"),
        )
        for filename, title, og_title, description, counterpart in pages:
            with self.subTest(source=filename):
                source = (ROOT / "en" / filename).read_text(encoding="utf-8")
                with tempfile.TemporaryDirectory() as directory:
                    rendered = Path(directory) / filename
                    rendered.write_text(source.replace("{{SITE_URL}}", PUBLIC_URL), encoding="utf-8")
                    self.assert_english_page_metadata(
                        rendered, title, og_title, description,
                        f"{PUBLIC_URL}en/{filename}", f"{PUBLIC_URL}{counterpart}",
                    )
        with tempfile.TemporaryDirectory(prefix=".english-metadata-", dir=ROOT) as directory:
            output = Path(directory) / "site"
            build_site.build(output)
            for filename, title, og_title, description, counterpart in pages:
                with self.subTest(build=filename):
                    self.assert_english_page_metadata(
                        output / "en" / filename, title, og_title, description,
                        f"{PUBLIC_URL}en/{filename}", f"{PUBLIC_URL}{counterpart}",
                    )
        contacts = (ROOT / "en" / "contacts.html").read_text(encoding="utf-8")
        self.assertIn('<a class="brand" href="./" aria-label="Horse Quizzes — Home">', contacts)

    def test_source_pages_have_exact_metadata(self):
        for filename, expected in PAGES.items():
            with self.subTest(filename=filename):
                source = (ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("Русскоязычные викторины на самые разные темы.", source)
                self.assertNotIn("Русскоязыные викторины на самые разные темы.", source)
                parser = HeadParser()
                parser.feed(source.replace("{{SITE_URL}}", PUBLIC_URL).replace("{{SITE_PATH}}", load_site_config(ROOT)["base_path"]))
                self.assert_metadata(parser, *expected)

    def test_quiz_share_pages_keep_individual_metadata(self):
        anatomy = self.parse(ROOT / "v" / "anatomy" / "index.html")
        self.assertEqual(anatomy.meta["og:title"], "Анатомия лошади")
        self.assertEqual(anatomy.meta["og:image"], f"{PUBLIC_URL}img/covers/anatomy.webp")
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
