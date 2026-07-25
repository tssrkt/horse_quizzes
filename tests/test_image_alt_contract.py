import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ImageAltContractTests(unittest.TestCase):
    def test_cms_has_one_quiz_level_alt_and_no_question_alt(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        quiz_fields = schema.split("  - name: quizzes\n", 1)[1]
        questions = quiz_fields.split("      - name: questions\n", 1)[1]
        before_questions = quiz_fields.split("      - name: questions\n", 1)[0]
        self.assertEqual(schema.count("- name: questionImagesAlt"), 1)
        self.assertIn("label: Общий alt для изображений вопросов", before_questions)
        self.assertIn("required: false", before_questions.split("- name: questionImagesAlt", 1)[1].split("- name: tags", 1)[0])
        self.assertIn("Используется для всех изображений вопросов этой викторины. Не указывайте правильный ответ.", before_questions)
        self.assertNotIn("name: image_alt", questions)

    def test_every_static_image_has_alt_and_brand_logos_are_decorative(self):
        pages = [ROOT / name for name in ("index.html", "quizzes.html", "quiz.html", "contacts.html", "404.html")]
        pages.extend((ROOT / "v").glob("*/index.html"))
        for page in pages:
            with self.subTest(page=page.relative_to(ROOT)):
                source = page.read_text(encoding="utf-8")
                for image in re.findall(r"<img\b[^>]*>", source):
                    self.assertRegex(image, r'\balt="[^"]*"')
                for logo in re.findall(r'<img class="brand-logo"[^>]*>', source):
                    self.assertIn('alt=""', logo)

    def test_dynamic_images_use_shared_alt_helpers(self):
        quiz_js = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        catalog_js = (ROOT / "js" / "quizzes.js").read_text(encoding="utf-8")
        self.assertIn("core.coverAlt(quiz)", quiz_js)
        self.assertIn("core.questionImageAlt(quiz)", quiz_js)
        self.assertNotIn("question.image_alt", quiz_js)
        self.assertIn('alt="Обложка викторины «${escapeHtml(quiz.title)}»"', catalog_js)


if __name__ == "__main__":
    unittest.main()
