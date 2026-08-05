import unittest
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IntroMarkupParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.strong = []
        self.links = []
        self._strong_text = None
        self._link = None

    def handle_starttag(self, tag, attrs):
        if tag == "strong":
            self._strong_text = ""
        elif tag == "a":
            self._link = {"attrs": dict(attrs), "text": ""}

    def handle_data(self, data):
        if self._strong_text is not None:
            self._strong_text += data
        if self._link is not None:
            self._link["text"] += data

    def handle_endtag(self, tag):
        if tag == "strong":
            self.strong.append(self._strong_text)
            self._strong_text = None
        elif tag == "a":
            self.links.append(self._link)
            self._link = None


class CatalogIntroContractTests(unittest.TestCase):
    def test_english_intro_keeps_required_semantics_and_inline_markup(self):
        html = (ROOT / "quizzes.html").read_text(encoding="utf-8")
        matches = re.findall(r'<template id="catalog-intro-english">(.*?)</template>', html, re.DOTALL)
        self.assertEqual(len(matches), 1, "Нужен ровно один шаблон английского вступления")
        intro = matches[0]
        parser = IntroMarkupParser()
        parser.feed(intro)
        self.assertEqual(parser.strong, ["словарные", "английские"])
        self.assertEqual(parser.links, [{
            "attrs": {"href": "https://tssrkt.github.io/quiz/v/english/"},
            "text": "«Экстерьера лошади»",
        }])
        self.assertIn("два типа викторин", intro)
        self.assertIn("тег «Словарь»", intro)
        self.assertIn("тег «English»", intro)
        self.assertIn("на обложках всех словарных викторин изображен всадник на лошади", intro)
        self.assertNotRegex(intro, r"<(?:p|div|section|button)\b")

    def test_intro_switch_is_rendered_with_initial_and_changed_section(self):
        javascript = (ROOT / "js/quizzes.js").read_text(encoding="utf-8")
        self.assertIn("section: getStateFromUrl(location.search, new Set()).section", javascript)
        self.assertIn("catalogIntro.innerHTML = catalogIntroHtml(state.section", javascript)
        self.assertIn("renderSections();", javascript)

    def test_link_and_strong_inherit_catalog_intro_typography(self):
        css = (ROOT / "css/style.css").read_text(encoding="utf-8")
        self.assertIn(".catalog-intro a,.catalog-intro strong{font-family:inherit;font-size:inherit;line-height:inherit;letter-spacing:inherit}", css)
        self.assertIn(".catalog-intro strong{color:inherit;font-weight:700}", css)
        self.assertIn(".catalog-intro a{display:inline;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none", css)


if __name__ == "__main__":
    unittest.main()
