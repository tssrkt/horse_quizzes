import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_site


class BilingualSiteTests(unittest.TestCase):
    def test_english_contacts_uses_approved_copy_and_preserves_copy_control(self):
        page = (build_site.ROOT / "en/contacts.html").read_text(encoding="utf-8")
        approved = (
            "This project was created and continues to grow thanks to the support of kind people. "
            "If you enjoy it too and would like to support it, here is my YooMoney number: "
            "4100116004998786. If you have any questions, suggestions for improving the site, "
            "spot an error, or are interested in my other projects, you can contact me through any "
            "of the services listed below. I’ll be happy to receive your feedback, comments, and suggestions."
        )
        copy_control = (
            '<span class="copy-donate" data-copy="4100116004998786" '
            'title="Click to copy" role="button" tabindex="0">4100116004998786</span>'
        )
        paragraph = page.split('<p class="contact-text">', 1)[1].split("</p>", 1)[0]
        self.assertEqual(paragraph.replace(copy_control, "4100116004998786"), approved)
        self.assertIn('<h1 class="page-title">Contact and Support</h1>', page)
        self.assertIn(copy_control, page)
        self.assertIn('<div class="copy-message" role="status" aria-live="polite"></div>', page)
        links = {
            "Author.Today": "https://author.today/u/tssrkt",
            "Telegram": "https://t.me/tssrkt",
            "VK": "https://vk.com/ada.king3d",
            "LiveLib": "https://www.livelib.ru/reader/ada_king",
        }
        for label, href in links.items():
            self.assertIn(
                f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
                f'{label} <span class="external-mark" aria-hidden="true">↗</span></a>',
                page,
            )
        self.assertEqual(page.count('<span class="external-mark" aria-hidden="true">↗</span>'), 4)
        common = (build_site.ROOT / "js/common.js").read_text(encoding="utf-8")
        self.assertIn("'YooMoney number copied.'", common)
        self.assertIn("event.key === 'Enter' || event.key === ' '", common)

    def test_english_home_uses_approved_copy_verbatim(self):
        page = (build_site.ROOT / "en/index.html").read_text(encoding="utf-8")
        approved = (
            "Test Your Knowledge While Having Fun",
            "Here you’ll find educational quizzes about horses and everything related to them. They’ll help you test your knowledge, refresh what you may have forgotten, and discover new and interesting facts.",
            "Quizzes are a simple and entertaining way to test yourself without exams, grades, or boring assignments. Sometimes a familiar subject turns out to be much deeper than it first appears, while an unexpected question can reveal gaps in your knowledge or spark an interest in something new. Some quizzes stand on their own, while others are grouped into entire series that you can work through in order, gradually exploring a topic and moving from one part to the next.",
            "Choose a quiz that interests you, answer the questions, and at the end you’ll receive a result based on the number of correct answers. There’s no need to register, compete with other participants, or worry about making mistakes. You can take a quiz again to refresh your memory, review the correct answers, and improve your result. If a quiz is part of a series, you can move on to the next part afterward and continue exploring the topic.",
            "A wrong answer isn’t a failure — it’s an opportunity to learn something you didn’t know before. Some questions can be quite challenging, so your result shouldn’t be treated as a strict assessment of your knowledge. Think of it instead as a small guide showing which topics you already know well and which ones you might want to explore further.",
            "These quizzes are intended primarily for learning, entertainment, and broadening your knowledge. They are not professional examinations or an official system for assessing expertise. The questions are prepared using publicly available sources, but the material may still contain inaccuracies. If you spot an error or would like to suggest a correction or clarification, please let us know through the contact page.",
            "The photographs used in the quizzes come from the project author’s personal archive. This collection was built up over many years, so unfortunately it is now difficult to identify the original source of every photograph. If you are the author of any of the photographs, or if you know their original source, please let us know through the contact page. A credit and link to the author or original source will be added beneath the relevant photograph with gratitude — the site already supports this.",
        )
        for text in approved:
            self.assertIn(text, page)
        for heading in ("Educational Quizzes", "How It Works", "Important", "Copyright"):
            self.assertIn(f"<h2>{heading}</h2>", page)
        self.assertIn('<a class="button" href="quizzes.html">Browse the Quizzes</a>', page)
        how_it_works = page.split("<h2>How It Works</h2>", 1)[1].split("</section>", 1)[0]
        self.assertEqual(how_it_works.count("<p>"), 2)
        for obsolete in ("Learn with quizzes", "Educational purpose", "Images and copyright", "Explore educational quizzes about horses"):
            self.assertNotIn(obsolete, page)

    def build(self, base_path):
        temporary = tempfile.TemporaryDirectory(prefix=".bilingual-", dir=build_site.ROOT)
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site"
        with mock.patch.dict(os.environ, {"BASE_PATH": base_path, "SITE_ORIGIN": "https://example.test"}):
            build_site.build(output)
        return output

    def assert_build(self, base_path):
        output = self.build(base_path)
        for relative in ("index.html", "quizzes.html", "contacts.html", "en/index.html", "en/quizzes.html", "en/contacts.html", "en/v/horse-breeds/index.html"):
            self.assertTrue((output / relative).is_file(), relative)
        self.assertFalse((output / "en/v/horse-breeds-en").exists())
        catalog = json.loads((output / "data/catalog-en.json").read_text(encoding="utf-8"))
        self.assertTrue(catalog["quizzes"])
        self.assertEqual({quiz["type"] for quiz in catalog["quizzes"]}, {"english"})
        self.assertTrue(all(quiz["published"] and quiz["public_slug"] == quiz["source_quiz"] for quiz in catalog["quizzes"]))
        self.assertNotIn("english", {tag["slug"] for tag in catalog["tags"]})
        page = (output / "en/v/horse-breeds/index.html").read_text(encoding="utf-8")
        root = f"https://example.test{base_path}"
        self.assertIn('<html lang="en">', page)
        self.assertIn(f'<link rel="canonical" href="{root}en/v/horse-breeds/">', page)
        self.assertIn(f'hreflang="ru" href="{root}v/horse-breeds/"', page)
        self.assertIn('../../../v/horse-breeds/', page)
        russian = (output / "v/horse-breeds/index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="ru">', russian)
        self.assertIn('../../en/v/horse-breeds/', russian)
        untranslated = next(quiz for quiz in json.loads((output / "data/catalog.json").read_text(encoding="utf-8"))["quizzes"] if quiz.get("type") not in {"english", "vocabulary"} and not (output / "en/v" / quiz["slug"]).exists())
        no_translation_page = (output / "v" / untranslated["slug"] / "index.html").read_text(encoding="utf-8")
        self.assertIn('../../en/quizzes.html', no_translation_page)
        for filename, counterpart in (("quizzes.html", "quizzes.html"), ("contacts.html", "contacts.html")):
            metadata_page = (output / "en" / filename).read_text(encoding="utf-8")
            root = f"https://example.test{base_path}"
            self.assertIn(f'<link rel="canonical" href="{root}en/{filename}">', metadata_page)
            self.assertIn(f'<link rel="alternate" hreflang="ru" href="{root}{counterpart}">', metadata_page)
            self.assertIn(f'<link rel="alternate" hreflang="en" href="{root}en/{filename}">', metadata_page)
            self.assertIn(f'<link rel="alternate" hreflang="x-default" href="{root}{counterpart}">', metadata_page)
            self.assertIn(f'<meta property="og:image" content="{root}img/site-preview.webp">', metadata_page)
            self.assertIn(f'<meta name="twitter:image" content="{root}img/site-preview.webp">', metadata_page)
        not_found = (output / "404.html").read_text(encoding="utf-8")
        self.assertIn(
            f'<nav class="language-switch" aria-label="Выбор языка">\n'
            f'        <a href="{base_path}" aria-current="page">RU</a>',
            not_found,
        )
        self.assertIn(f'<a href="{base_path}en/" lang="en">EN</a>', not_found)
        self.assertIn(f'<a href="{base_path}index.html">Главная</a>', not_found)
        self.assertIn(f'<a href="{base_path}quizzes.html">Викторины</a>', not_found)
        self.assertIn(f'<a href="{base_path}contacts.html">Контакты</a>', not_found)
        return output

    def test_not_found_localizer_updates_the_complete_english_header(self):
        javascript = (build_site.ROOT / "js/not-found.js").read_text(encoding="utf-8")
        for text in ("Home", "Quizzes", "Contacts", "Main navigation", "Language", "Horse Quizzes — Home", "Open menu"):
            self.assertIn(repr(text), javascript)
        for path in ("en/", "en/quizzes.html", "en/contacts.html"):
            self.assertIn(f"`${{basePath}}{path}`", javascript)
        self.assertIn("switchLinks[0]?.removeAttribute('aria-current')", javascript)
        self.assertIn("switchLinks[1]?.setAttribute('aria-current', 'page')", javascript)
        template = (build_site.ROOT / "404.html").read_text(encoding="utf-8")
        self.assertLess(template.index('js/not-found.js'), template.index('js/common.js'))

    def test_github_pages_base_path(self):
        self.assert_build("/horse_quizzes/")

    def test_root_base_path(self):
        self.assert_build("/")

    def test_english_template_has_no_russian_catalog_mode(self):
        page = (build_site.ROOT / "en/quizzes.html").read_text(encoding="utf-8")
        self.assertNotIn("Английский для конников", page)
        self.assertNotIn("vocabulary", page)
        for text in ("Choose a Quiz", "By date", "By difficulty", "Alphabetical", "Loading quizzes"):
            self.assertIn(text, page)

    def test_english_catalog_uses_approved_intro_and_english_quiz_links(self):
        page = (build_site.ROOT / "en/quizzes.html").read_text(encoding="utf-8")
        approved = "If you’re not sure where to start, we recommend beginning with the easiest quiz: Horse Breeds. If horse coat colors are more your thing, try Horse Colors. To test your general knowledge about horses, choose Horse Terms, and if you’d like to understand how traits are inherited, take Horse Genetics. At the end of each quiz, you’ll find a link to the next one in the same series — or maybe you won’t; that part is a bit of a gamble. Also, keep in mind that if the cover shows only a horse’s head, the quiz contains photographs, while a full-body horse on the cover means there are no photos inside. Enjoy the quizzes!"
        text_only = page
        for markup in (
            '<a href="v/horse-breeds/" target="_blank" rel="noopener noreferrer">',
            '<a href="v/horse-colors/" target="_blank" rel="noopener noreferrer">',
            '<a href="v/horse-words/" target="_blank" rel="noopener noreferrer">',
            '<a href="v/horse-genetics/" target="_blank" rel="noopener noreferrer">',
        ):
            text_only = text_only.replace(markup, "")
        text_only = text_only.replace("</a>", "")
        self.assertIn(approved, text_only)
        self.assertIn('<h1 class="page-title">Choose a Quiz</h1><p class="catalog-intro" id="catalog-intro"', page)
        self.assertNotIn("Horse knowledge", page)
        self.assertNotIn('class="lead" id="catalog-intro"', page)
        self.assertNotIn("Only complete, published English translations are listed here.", page)
        links = {
            "Horse Breeds": "v/horse-breeds/", "Horse Colors": "v/horse-colors/",
            "Horse Terms": "v/horse-words/", "Horse Genetics": "v/horse-genetics/",
        }
        for label, href in links.items():
            self.assertIn(f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>', page)
            self.assertNotIn(f'href="../{href}"', page)


if __name__ == "__main__":
    unittest.main()
