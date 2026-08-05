import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CatalogIntroContractTests(unittest.TestCase):
    def test_english_intro_markup_is_exact(self):
        html = (ROOT / "quizzes.html").read_text(encoding="utf-8")
        expected = ('На данной вкладке есть два типа викторин: <strong>словарные</strong>, где вы изучаете конные термины на буржуйском, и <strong>английские</strong>, которые представляют собой переводы существующих на сайте русских викторин. Если в конном английском вы пока не сильны, рекомендуем начать со словарных, а именно с <a href="https://tssrkt.github.io/quiz/v/english/">«Экстерьера лошади»</a>. Ну или с любой другой — сложность у них примерно одинаковая. Также обратите внимание, что на обложках всех словарных викторин изображен всадник на лошади.')
        self.assertIn(f'<template id="catalog-intro-english">{expected}</template>', html)

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
