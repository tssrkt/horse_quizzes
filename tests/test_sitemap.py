import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from tools import build_site


SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"
NS = {"sm": SITEMAP_NS, "xhtml": XHTML_NS}


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = None
        self.alternates = {}

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        values = dict(attrs)
        if values.get("rel") == "canonical":
            self.canonical = values.get("href")
        elif values.get("rel") == "alternate" and values.get("hreflang"):
            self.alternates[values["hreflang"]] = values.get("href")


class SitemapTests(unittest.TestCase):
    def build(self, base_path):
        temporary = tempfile.TemporaryDirectory(prefix=".sitemap-", dir=build_site.ROOT)
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site"
        with mock.patch.dict(
            os.environ,
            {"SITE_ORIGIN": "https://tssrkt.github.io", "BASE_PATH": base_path},
        ):
            catalog = build_site.build(output)
        return output, catalog

    @staticmethod
    def entries(output):
        raw = (output / "sitemap.xml").read_bytes()
        root = ET.fromstring(raw)
        return raw, root.findall("sm:url", NS)

    @staticmethod
    def page_for_url(output, location, base_path):
        path = urlsplit(location).path
        relative = path.removeprefix(base_path)
        if not relative or relative.endswith("/"):
            relative += "index.html"
        return output / relative

    def assert_sitemap(self, base_path):
        output, catalog = self.build(base_path)
        raw, entries = self.entries(output)
        locations = [entry.findtext("sm:loc", namespaces=NS) for entry in entries]
        prefix = f"https://tssrkt.github.io{base_path}"

        self.assertTrue(raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertEqual(len(locations), 67)
        self.assertEqual(len(locations), len(set(locations)))
        self.assertTrue(all(location.startswith(prefix) for location in locations))
        self.assertTrue(all(urlsplit(location).scheme == "https" for location in locations))
        self.assertFalse(any("{{SITE_" in location for location in locations))

        expected_static = {
            prefix,
            f"{prefix}quizzes.html",
            f"{prefix}contacts.html",
            f"{prefix}en/",
            f"{prefix}en/quizzes.html",
            f"{prefix}en/contacts.html",
        }
        self.assertTrue(expected_static.issubset(locations))
        for forbidden in ("404.html", "quiz.html", "en/quiz.html"):
            self.assertNotIn(f"{prefix}{forbidden}", locations)
        self.assertFalse(any("?" in location or "#" in location for location in locations))
        self.assertFalse(any("/en/v/" in location and location.rstrip("/").endswith("-en") for location in locations))

        published = catalog["quizzes"]
        russian = [quiz for quiz in published if quiz.get("type") != "english"]
        vocabulary = [quiz for quiz in russian if quiz.get("type") == "vocabulary"]
        ordinary = [quiz for quiz in russian if quiz.get("type") != "vocabulary"]
        english = [quiz for quiz in published if quiz.get("type") == "english"]
        self.assertEqual((len(ordinary), len(vocabulary), len(english)), (27, 7, 27))
        for quiz in russian:
            self.assertIn(f"{prefix}v/{quiz['slug']}/", locations)
        for quiz in english:
            self.assertIn(f"{prefix}en/v/{quiz['source_quiz']}/", locations)
        self.assertFalse(any(f"{prefix}en/v/{quiz['slug']}/" in locations for quiz in vocabulary))

        for entry, location in zip(entries, locations):
            page_path = self.page_for_url(output, location, base_path)
            self.assertTrue(page_path.is_file(), location)
            parser = MetadataParser()
            parser.feed(page_path.read_text(encoding="utf-8"))
            self.assertEqual(parser.canonical, location)
            sitemap_alternates = {
                link.attrib["hreflang"]: link.attrib["href"]
                for link in entry.findall("xhtml:link", NS)
            }
            self.assertEqual(sitemap_alternates, parser.alternates)
            if sitemap_alternates:
                self.assertEqual(sitemap_alternates["x-default"], sitemap_alternates["ru"])
                counterpart = sitemap_alternates["en" if location == sitemap_alternates["ru"] else "ru"]
                counterpart_entry = entries[locations.index(counterpart)]
                reciprocal = {
                    link.attrib["hreflang"]: link.attrib["href"]
                    for link in counterpart_entry.findall("xhtml:link", NS)
                }
                self.assertEqual(reciprocal, sitemap_alternates)
        return output

    def test_github_pages_subpath_sitemap(self):
        self.assert_sitemap("/horse_quizzes/")

    def test_root_deployment_sitemap(self):
        self.assert_sitemap("/")


if __name__ == "__main__":
    unittest.main()
