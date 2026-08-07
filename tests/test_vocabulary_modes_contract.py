import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VocabularyModesContractTests(unittest.TestCase):
    def test_controls_and_accessible_hints_are_vocabulary_only(self):
        javascript = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        self.assertIn("if (quiz.type !== 'vocabulary') return '';", javascript)
        self.assertIn('type="checkbox"', javascript)
        self.assertIn('class="vocabulary-mode" data-tooltip="${hint}" tabindex="0"', javascript)
        self.assertNotIn('class="vocabulary-mode" title=', javascript)
        self.assertIn('aria-describedby="mode-hint-${value}"', javascript)
        self.assertIn("Вам показывают английские слова, вы выбираете русский перевод", javascript)
        self.assertIn("Вам показывают русские слова, вы выбираете английский перевод", javascript)
        self.assertIn("Вам показывают русские слова, вы вводите английский перевод с клавиатуры", javascript)
        self.assertIn("answerTypingQuestion", javascript)
        self.assertIn("data-typing-form", javascript)
        self.assertNotIn("disabled aria-disabled=\"true\"", javascript)

    def test_layout_wraps_and_has_keyboard_focus(self):
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".vocabulary-modes{display:flex;justify-content:center;flex-wrap:wrap", css)
        self.assertIn("outline:3px solid #9a74c5", css)
        self.assertIn(".vocabulary-mode:focus-within", css)
        self.assertIn(".typing-answer input:focus-visible", css)
        self.assertIn("@media(max-width:520px){.typing-answer", css)

    def test_part_selector_is_radio_wrapped_and_vocabulary_only(self):
        javascript = (ROOT / "js" / "quiz.js").read_text(encoding="utf-8")
        css = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('role="radiogroup"', javascript)
        self.assertIn('type="radio"', javascript)
        self.assertIn("if (parts.length < 2) return '';", javascript)
        self.assertIn("quiz-selection:${sourceQuiz.slug}", javascript)
        self.assertIn("quiz-progress:${sourceQuiz.slug}:${selectedPartId}:${selectedModes.join('+')}", javascript)
        self.assertIn("core.totalVocabularyWordCount(sourceQuiz)", javascript)
        self.assertIn("из ${quiz.questions.length}", javascript)
        self.assertIn("max=\"${quiz.questions.length}\"", javascript)
        self.assertIn("${escapeHtml(part.title)} (${escapeHtml(core.formatQuestionCount(part.word_count, 'vocabulary'))})", javascript)
        self.assertNotIn("${escapeHtml(part.title)} — ${escapeHtml(core.formatQuestionCount", javascript)
        self.assertIn(".vocabulary-parts{display:flex;justify-content:center;flex-wrap:wrap", css)
        self.assertIn(".vocabulary-part i{", css)


if __name__ == "__main__":
    unittest.main()
