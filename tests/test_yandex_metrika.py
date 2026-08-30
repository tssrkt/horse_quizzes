import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from tools import build_site


COUNTER_ID = "112089914"
INIT = "ym(112089914, 'init'"
TAG_URL = "https://mc.yandex.ru/metrika/tag.js?id=112089914"
WATCH_URL = "https://mc.yandex.ru/watch/112089914"


class YandexMetrikaTests(unittest.TestCase):
    def build(self, base_path="/horse_quizzes/"):
        temporary = tempfile.TemporaryDirectory(prefix=".metrika-", dir=build_site.ROOT)
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site"
        with mock.patch.dict(
            os.environ,
            {"SITE_ORIGIN": "https://example.test", "BASE_PATH": base_path},
        ):
            build_site.build(output)
        return output

    @staticmethod
    def sitemap_pages(output, base_path):
        root = ET.parse(output / "sitemap.xml").getroot()
        pages = []
        for element in root.iter():
            if not element.tag.endswith("loc"):
                continue
            relative = urlsplit(element.text).path.removeprefix(base_path)
            if not relative or relative.endswith("/"):
                relative += "index.html"
            pages.append(output / relative)
        return pages

    def assert_counter(self, path):
        html = path.read_text(encoding="utf-8")
        self.assertEqual(html.count("<!-- Yandex.Metrika counter -->"), 1, path)
        self.assertEqual(html.count("<!-- /Yandex.Metrika counter -->"), 1, path)
        self.assertEqual(html.count(INIT), 1, path)
        self.assertEqual(html.count(TAG_URL), 1, path)
        self.assertEqual(html.count(WATCH_URL), 1, path)
        ids = set(re.findall(r"mc\.yandex\.ru/(?:watch/|metrika/tag\.js\?id=)(\d+)", html))
        self.assertEqual(ids, {COUNTER_ID}, path)
        self.assertLess(html.index(TAG_URL), html.index("</head>"), path)
        self.assertGreater(html.index(WATCH_URL), html.index("<body"), path)

    def test_counter_is_present_once_on_every_public_and_support_page(self):
        output = self.build()
        pages = self.sitemap_pages(output, "/horse_quizzes/")
        self.assertTrue(pages)
        for path in pages + [output / "404.html", output / "quiz.html"]:
            with self.subTest(path=path.relative_to(output)):
                self.assert_counter(path)
        technical = (output / "quiz.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex,follow">', technical)

    def test_counter_is_base_path_independent(self):
        output = self.build("/")
        for path in self.sitemap_pages(output, "/"):
            with self.subTest(path=path.relative_to(output)):
                self.assert_counter(path)


if __name__ == "__main__":
    unittest.main()
