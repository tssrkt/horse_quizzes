import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateContractTests(unittest.TestCase):
    def test_pages_cms_tag_titles_and_references_use_explicit_fields(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        tags_collection = schema.split("  - name: tags\n", 1)[1].split("  - name: quizzes\n", 1)[0]
        self.assertIn('template: "{fields.slug}.json"', tags_collection)
        self.assertIn("field: false", tags_collection)
        self.assertRegex(tags_collection, r"view:\s+fields: \[name, slug, published\]\s+primary: name")
        self.assertIn("sort: [name]", tags_collection)
        self.assertIn("search: [name, slug]", tags_collection)
        self.assertRegex(tags_collection, r"default:\s+sort: name\s+order: asc")
        self.assertNotIn("name: order", tags_collection)

        quiz_collection = schema.split("  - name: quizzes\n", 1)[1]
        self.assertIn('template: "{fields.slug}.json"', quiz_collection)
        reference = quiz_collection.split("      - name: tags\n", 1)[1].split("      - name: questions\n", 1)[0]
        self.assertIn("type: reference", reference)
        self.assertIn("collection: tags", reference)
        self.assertIn('value: "{fields.slug}"', reference)
        self.assertIn('label: "{fields.name}"', reference)
        self.assertNotIn('label: "{name}"', reference)

        previous_quiz = quiz_collection.split("      - name: previous_quiz\n", 1)[1].split("      - name: questions\n", 1)[0]
        self.assertIn("label: Предыдущая викторина", previous_quiz)
        self.assertIn("type: reference", previous_quiz)
        self.assertIn("required: false", previous_quiz)
        self.assertIn("collection: quizzes", previous_quiz)
        self.assertIn("multiple: false", previous_quiz)
        self.assertIn('value: "{fields.slug}"', previous_quiz)
        self.assertIn('label: "{fields.title}"', previous_quiz)

    def test_tag_files_keep_technical_names_and_russian_labels(self):
        required = {
            "horses.json": ("Масти", "horses"),
            "images.json": ("Картинки", "images"),
            "genetics.json": ("Генетика", "genetics"),
        }
        tag_root = ROOT / "data" / "tags"
        tag_paths = sorted(tag_root.glob("*.json"))
        self.assertTrue(tag_paths)
        for path in tag_paths:
            tag = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.stem, tag["slug"])
            self.assertIsInstance(tag["name"], str)
            self.assertTrue(tag["name"].strip())
            self.assertEqual(tag["published"], True)
        self.assertTrue(set(required).issubset(path.name for path in tag_paths))
        for filename, (name, slug) in required.items():
            tag = json.loads((tag_root / filename).read_text(encoding="utf-8"))
            self.assertEqual(tag, {"name": name, "slug": slug, "published": True})

        horse = json.loads((ROOT / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        self.assertEqual(horse["tags"], ["horses", "images"])
        self.assertEqual(horse["difficulty"], "low")

    def test_cms_has_required_single_difficulty_select(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        block = schema.split("      - name: difficulty\n", 1)[1].split("      - name: short_description\n", 1)[0]
        self.assertIn("label: Уровень сложности", block)
        self.assertIn("type: select", block)
        self.assertIn("required: true", block)
        self.assertIn("default: low", block)
        self.assertNotIn("multiple:", block)
        self.assertEqual(re.findall(r"- name: (low|medium|high)\s+label: (Низкая|Средняя|Высокая)", block), [("low", "Низкая"), ("medium", "Средняя"), ("high", "Высокая")])

    def test_cms_requires_one_correct_answer_selection(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        questions = schema.split("      - name: questions\n", 1)[1]
        block = questions.split("          - name: correct_answer_id\n", 1)[1].split("          - name: explanation\n", 1)[0]
        self.assertIn("label: Правильный вариант", block)
        self.assertIn("type: select", block)
        self.assertIn("required: true", block)
        self.assertIn("multiple: false", block)
        self.assertIn("values: [answer-01, answer-02, answer-03, answer-04, answer-05, answer-06]", block)
        self.assertNotIn("name: answer-", block)
        self.assertNotRegex(questions, r"(?m)^\s+- name: correct\s*$")

    def test_existing_correct_answer_ids_are_scalar_cms_options(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        questions = schema.split("      - name: questions\n", 1)[1]
        block = questions.split("          - name: correct_answer_id\n", 1)[1].split("          - name: explanation\n", 1)[0]
        match = re.search(r"(?m)^\s+values:\s*\[([^]]+)]\s*$", block)
        self.assertIsNotNone(match)
        configured = {value.strip() for value in match.group(1).split(",")}

        quiz = json.loads((ROOT / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(quiz["questions"]), 24)
        for index, question in enumerate(quiz["questions"]):
            selected = question["correct_answer_id"]
            self.assertIn(selected, configured, f"questions.{index}.correct_answer_id")
            self.assertIn(selected, {answer["id"] for answer in question["answers"]})

    def test_catalog_card_has_difficulty_before_tags_and_description_is_three_pixels_larger(self):
        javascript = (ROOT / "js" / "quizzes.js").read_text(encoding="utf-8")
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertLess(javascript.index('class="quiz-card-difficulty"'), javascript.index('class="quiz-tags"'))
        self.assertIn("Сложность: ${DIFFICULTY_LABELS[quiz.difficulty]}", javascript)
        self.assertIn(".quiz-card-description{font-size:calc(1rem + 3px)}", css)
        self.assertIn(".quiz-card .quiz-card-description{font-size:calc(.9rem + 3px)}", css)

    def test_result_page_renders_optional_next_quiz_link(self):
        javascript = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('class="next-quiz"', javascript)
        self.assertIn('class="next-quiz__label">Следующая викторина', javascript)
        self.assertIn("core.quizPath(nextQuiz.slug, location.href)", javascript)
        self.assertIn("nextQuiz ?", javascript)
        self.assertIn(".next-quiz{margin-top:8px;text-align:center}", stylesheet)
        self.assertNotIn(".next-quiz{margin-top:15px", stylesheet)
        self.assertIn(".next-quiz__link:hover{", stylesheet)

    def test_vocabulary_result_renders_only_computed_next_link(self):
        javascript = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        result_renderer = javascript.split("  function renderResult() {", 1)[1].split("  async function load() {", 1)[0]
        self.assertNotIn("Предыдущая викторина", result_renderer)
        self.assertNotIn("previousQuiz", result_renderer)
        self.assertIn("${nextQuizBlock}", result_renderer)

    def test_catalog_cards_have_bounded_horizontal_and_square_mobile_layouts(self):
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".quiz-card{grid-template-columns:220px minmax(0,1fr);max-height:440px}", css)
        self.assertIn(".quiz-cover{width:220px;height:100%;min-height:220px;aspect-ratio:auto}", css)
        self.assertIn("object-fit:cover;object-position:right center", css)
        self.assertIn("@media(max-width:700px){.quiz-card{grid-template-columns:1fr;max-height:none}", css)
        self.assertIn(".quiz-cover{width:100%;height:auto;min-height:0;aspect-ratio:1}", css)
        self.assertIn(".quiz-cover img{object-position:center}", css)

    def test_cms_short_description_has_250_character_limit(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        block = schema.split("      - name: short_description\n", 1)[1].split("      - name: intro\n", 1)[0]
        self.assertIn("type: text", block)
        self.assertIn("maxlength: 250", block)

    def test_removed_level_tag_is_absent_everywhere_that_is_published(self):
        removed_slug = "begin" + "ner"
        self.assertFalse((ROOT / "data" / "tags" / f"{removed_slug}.json").exists())
        horse = json.loads((ROOT / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        self.assertNotIn(removed_slug, horse["tags"])

    def test_removed_animals_tag_is_absent_from_tags_and_every_quiz(self):
        removed_slug = "animals"
        self.assertFalse((ROOT / "data" / "tags" / f"{removed_slug}.json").exists())
        for quiz_path in (ROOT / "data" / "quizzes").glob("*.json"):
            quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
            self.assertNotIn(removed_slug, quiz["tags"], quiz_path.name)

    def test_current_quiz_has_persisted_stable_ids(self):
        quiz = json.loads((ROOT / "data" / "quizzes" / "horse-colors.json").read_text(encoding="utf-8"))
        question_count = len(quiz["questions"])
        self.assertGreater(question_count, 0)
        self.assertEqual([question["id"] for question in quiz["questions"]], [f"question-{index:02d}" for index in range(1, question_count + 1)])
        self.assertTrue(all([answer["id"] for answer in question["answers"]] == [f"answer-{index:02d}" for index in range(1, 5)] for question in quiz["questions"]))
        self.assertEqual(
            [question["image"] for question in quiz["questions"]],
            [f"img/quiz/horse-colors/{index:02d}.webp" for index in range(1, question_count + 1)],
        )

    def test_cms_schema_preserves_hidden_ids_and_merge(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        self.assertNotIn("Уникальный идентификатор", schema)
        self.assertNotIn("{id}", schema)
        self.assertEqual(len(re.findall(r"(?m)^\s+- name: id\s*$", schema)), 5)
        hidden_id = r"- name: id\s+type: string\s+hidden: true\s+required: false"
        self.assertEqual(len(re.findall(hidden_id, schema)), 2)
        self.assertRegex(schema, r"settings:\s+content:\s+merge: true")
        self.assertIn('summary: "{index}. {question}"', schema)
        self.assertIn('summary: "Вариант {index}: {text}"', schema)

    def test_cms_list_summaries_use_visual_indexes_only(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        questions = schema.split("      - name: questions\n", 1)[1]
        question_list = questions.split("        fields:\n", 1)[0]
        answers = questions.split("          - name: answers\n", 1)[1].split("            fields:\n", 1)[0]
        self.assertIn('collapsed: true\n            summary: "{index}. {question}"', question_list)
        self.assertIn('collapsed: true\n                summary: "Вариант {index}: {text}"', answers)

        for quiz_path in (ROOT / "data" / "quizzes").glob("*.json"):
            quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
            for question in quiz["questions"]:
                self.assertNotRegex(question["question"], r"^\s*\d+\.\s")
                for answer in question["answers"]:
                    self.assertNotRegex(answer["text"], r"^\s*Вариант\s+\d+\s*:")

    def test_cms_hides_answer_text_label_without_changing_field(self):
        schema = (ROOT / ".pages.yml").read_text(encoding="utf-8")
        answers = schema.split("          - name: answers\n", 1)[1].split("          - name: correct_answer_id\n", 1)[0]
        text_field = answers.split("              - name: text\n", 1)[1]
        self.assertRegex(text_field, r"^\s*label: false\s+type: string\s+required: true")
        self.assertNotIn("Текст варианта", answers)

        for quiz_path in (ROOT / "data" / "quizzes").glob("*.json"):
            quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
            self.assertTrue(all("text" in answer for question in quiz["questions"] for answer in question["answers"]))

    def test_json_and_question_images_are_cache_busted(self):
        catalog_js = (ROOT / "js" / "quizzes.js").read_text(encoding="utf-8")
        quiz_js = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        self.assertIn("{ cache: 'no-store' }", catalog_js)
        self.assertGreaterEqual(quiz_js.count("{ cache: 'no-store' }"), 2)
        self.assertIn("contentVersion", quiz_js)
        self.assertIn("core.versionedUrl(question.image, quiz.content_version)", quiz_js)
        self.assertNotRegex(quiz_js, r"fetch\(`data/quizzes/\$\{encodeURIComponent\(slug\)\}\.json`\)")

    def test_image_css_uses_intrinsic_ratio_and_800_pixel_cap(self):
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".question-image{width:800px;max-width:100%;margin:0 auto 25px}", css)
        self.assertIn(".question-image img{width:800px;max-width:100%;height:auto", css)
        question_rule = re.search(r"\.question-image img\{([^}]+)\}", css).group(1)
        self.assertNotIn("object-fit:cover", question_rule)
        self.assertNotIn("max-height", question_rule)

    def test_wide_question_layout_and_no_image_fallback(self):
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        quiz_js = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        self.assertIn(".content-narrow.quiz-layout-wide{width:min(100% - 32px,1400px)}", css)
        self.assertIn("grid-template-columns:800px 500px", css)
        self.assertIn("@media(min-width:1432px)", css)
        self.assertIn("const withImage = Boolean(question.image);", quiz_js)
        self.assertIn("setWideLayout(withImage);", quiz_js)
        self.assertIn("question-card question-card--with-image", quiz_js)
        self.assertIn(": `<section class=\"question-card\">${questionContent}</section>`", quiz_js)

    def test_no_image_question_uses_full_card_width(self):
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".question-card:not(.question-card--with-image) .question-content{width:100%}", css)
        self.assertIn(".quiz-progress>span{flex:0 0 auto;white-space:nowrap}", css)
        self.assertIn(".quiz-progress progress{flex:1 1 auto;width:auto;min-width:0", css)
        self.assertIn(".question-content .answer-option{width:100%;min-width:0}", css)
        self.assertIn("@media(max-width:520px){.quiz-progress{align-items:stretch;flex-direction:column", css)

    def test_answer_and_feedback_text_are_three_pixels_larger(self):
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        rule = ".answer-option>span:not(.answer-icon):not(.visually-hidden),.answer-feedback>strong,.answer-feedback>p{font-size:calc(1rem + 3px)}"
        self.assertIn(rule, css)
        self.assertNotIn(".answer-feedback{font-size:calc(1rem + 3px)", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
