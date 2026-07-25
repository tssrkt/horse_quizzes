"""Optional real-browser scenarios; requires Python Playwright and installed Chrome."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / f".ui-test-profile-{os.getpid()}"
BASE_URL = "http://127.0.0.1:8766"
QUIZ_URL = f"{BASE_URL}/quiz.html?quiz=horse-colors"
SHARE_QUIZ_URL = "https://tssrkt.github.io/quiz/v/horse-colors/"
QUIZ = json.loads((ROOT / "_site/data/quizzes/horse-colors.json").read_text(encoding="utf-8"))
DRAFT_PATH = ROOT / "_site/data/quizzes/ui-draft.json"
BROKEN_PATH = ROOT / "_site/data/quizzes/ui-broken.json"


def chosen_id(question, correct):
    if correct:
        return question["correct_answer_id"]
    return next(answer["id"] for answer in question["answers"] if answer["id"] != question["correct_answer_id"])


def wait_next(page, index):
    if index + 1 < len(QUIZ["questions"]):
        page.get_by_text(f"Вопрос {index + 2} из {len(QUIZ['questions'])}").wait_for(timeout=2500)
    else:
        page.get_by_text("Викторина завершена").wait_for(timeout=2500)


def start_clean(page):
    page.goto(QUIZ_URL)
    page.evaluate("localStorage.clear()")
    page.reload()
    page.get_by_role("button", name="Начать викторину").click()


def all_correct(page):
    start_clean(page)
    for index, question in enumerate(QUIZ["questions"]):
        page.locator(f'[data-answer="{chosen_id(question, True)}"]').click()
        page.get_by_text("Верно!").wait_for()
        assert page.locator(".answer-option.is-correct .answer-icon").inner_text() == "✓"
        wait_next(page, index)
    assert page.locator(".result-summary").inner_text() == f"Ваш результат: {len(QUIZ['questions'])} из {len(QUIZ['questions'])} (100%)"
    recommendation = page.locator(".result-recommendation")
    assert recommendation.get_by_role("heading").count() == 0
    explanation = recommendation.locator(":scope > p")
    assert explanation.inner_text().startswith("Отличный результат! Вы правильно ответили")
    assert "Отличный результат!\n" not in explanation.inner_text()
    assert recommendation.locator(".result-recommendation__articles-content").inner_text().count("📖") == 1
    page.evaluate("Object.defineProperty(navigator, 'share', {value: async payload => { window.__sharePayload = payload }, configurable: true})")
    page.get_by_role("button", name="Поделиться результатом").click()
    page.wait_for_function("window.__sharePayload")
    payload = page.evaluate("window.__sharePayload")
    assert payload["text"] == f"Мой результат — {len(QUIZ['questions'])} из {len(QUIZ['questions'])} (100%) в викторине «{QUIZ['title']}». А какой у вас? Проверьте: {SHARE_QUIZ_URL}"
    assert "url" not in payload
    assert "\n" not in payload["text"]
    assert page.get_by_role("button", name="Telegram").count() == 0
    assert page.get_by_role("button", name="ВКонтакте").count() == 0


def all_wrong(page):
    start_clean(page)
    for index, question in enumerate(QUIZ["questions"]):
        page.locator(f'[data-answer="{chosen_id(question, False)}"]').click()
        page.get_by_text("Неверно", exact=True).wait_for()
        assert page.locator(".answer-option.is-wrong .answer-icon").inner_text() == "×"
        assert page.locator(".answer-option.is-correct .answer-icon").inner_text() == "✓"
        feedback_text = page.locator(".answer-feedback").inner_text()
        assert question["explanation"].strip() in feedback_text, f"Вопрос {index + 1}: {feedback_text!r}"
        if index == 0:
            page.wait_for_timeout(1000)
            assert page.get_by_text(f"Вопрос 1 из {len(QUIZ['questions'])}").is_visible()
        page.locator("[data-next]").click()
        wait_next(page, index)
    assert page.locator(".result-summary").inner_text() == f"Ваш результат: 0 из {len(QUIZ['questions'])} (0%)"
    recommendation = page.locator(".result-recommendation")
    assert recommendation.is_visible()
    assert page.get_by_role("button", name="Пройти еще раз", exact=True).is_visible()
    assert "Что ж, некоторые вопросы оказались непростыми — и это отличный повод узнать больше! Если желаете разобраться в теме глубже, откройте сборник статей о лошадках, а затем попробуйте пройти викторину еще раз. Наверняка после этого результат вас приятно удивит." in recommendation.inner_text()
    assert "Попробуйте пройти викторину ещё раз." not in page.locator(".result-card").inner_text()
    articles = recommendation.locator(".result-recommendation__articles")
    assert articles.get_attribute("href") == "https://author.today/work/439719"
    assert articles.get_attribute("target") == "_blank"
    assert "noopener" in articles.get_attribute("rel")
    assert articles.inner_text().count("📖") == 1
    page.set_viewport_size({"width": 1440, "height": 900})
    actions_before = page.locator(".share-actions").bounding_box()
    articles.hover()
    page.wait_for_timeout(200)
    hover_style = articles.evaluate("element => ({ transform: getComputedStyle(element).transform, filter: getComputedStyle(element).filter })")
    assert hover_style["transform"] != "none"
    assert hover_style["filter"] != "none"
    assert page.locator(".share-actions").bounding_box() == actions_before
    hover_style = articles.evaluate("element => ({ decoration: getComputedStyle(element).textDecorationLine, background: getComputedStyle(element).backgroundColor })")
    assert hover_style["decoration"] == "none"
    articles.focus()
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")
    assert articles.evaluate("element => element.matches(':focus-visible')")
    assert articles.evaluate("element => getComputedStyle(element).transform") != "none"
    for width in (1440, 375):
        page.set_viewport_size({"width": width, "height": 900})
        assert not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        assert recommendation.is_visible()
    page.evaluate("Object.defineProperty(navigator, 'share', {value: undefined, configurable: true})")
    page.locator("[data-share]").click()
    page.get_by_text("Результат скопирован.").wait_for()
    page.locator(".share-status").evaluate("element => { element.textContent = '' }")
    page.locator("[data-copy]").click()
    page.get_by_text("Результат скопирован.").wait_for()
    assert recommendation.get_by_role("link", name="↻ Пройти викторину еще раз").count() == 0
    page.locator("[data-restart]").click()
    page.locator("#question-position").wait_for()
    saved = page.evaluate("JSON.parse(localStorage.getItem('quiz-progress:horse-colors'))")
    assert saved["current_index"] == 0
    assert saved["correct_count"] == 0
    assert saved["answers"] == {}
    assert saved["completed"] is False


def mixed_with_reload(context, page):
    start_clean(page)
    first = QUIZ["questions"][0]
    page.locator(f'[data-answer="{chosen_id(first, True)}"]').click()
    wait_next(page, 0)
    second = QUIZ["questions"][1]
    page.locator(f'[data-answer="{chosen_id(second, False)}"]').click()
    page.get_by_text("Неверно", exact=True).wait_for()
    page.locator("[data-next]").click()
    page.get_by_text(f"Вопрос 3 из {len(QUIZ['questions'])}").wait_for()
    page.close()
    page = context.new_page()
    page.goto(QUIZ_URL)
    page.get_by_role("button", name="Продолжить").click()
    page.get_by_text(f"Вопрос 3 из {len(QUIZ['questions'])}").wait_for()
    for index in range(2, len(QUIZ["questions"])):
        question = QUIZ["questions"][index]
        answer_id = chosen_id(question, index == 2)
        page.locator(f'[data-answer="{answer_id}"]').click()
        if index == 2:
            wait_next(page, index)
        else:
            page.locator("[data-next]").click()
            wait_next(page, index)
    expected_percent = round(2 / len(QUIZ["questions"]) * 100)
    assert page.locator(".result-summary").inner_text() == f"Ваш результат: 2 из {len(QUIZ['questions'])} ({expected_percent}%)"
    return page


def adaptive_checks(page):
    for width in (360, 768, 1024, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        start_clean(page)
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        assert not overflow, f"Горизонтальное переполнение при {width}px"
        image = page.locator(".question-image img")
        if image.count():
            assert image.bounding_box()["width"] <= width
        question = QUIZ["questions"][0]
        page.locator(f'[data-answer="{chosen_id(question, False)}"]').click()
        page.get_by_text(question["explanation"]).wait_for()
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        assert not overflow, f"Переполнение пояснения при {width}px"


def catalog_card_checks(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/quizzes.html")
    card = page.locator('.quiz-card:has(.quiz-card-link[href="/v/horse-colors/"])')
    page.locator(".quiz-card").first.wait_for()
    if card.count() == 0:
        page.get_by_role("button", name="Страница 2", exact=True).click()
    card.wait_for()
    criterion = page.locator("#sort-criterion")
    direction = page.locator("[data-sort-direction]")
    assert criterion.input_value() == "date"
    assert direction.inner_text() == "↓"
    assert direction.get_attribute("title") == "Сначала новые"
    assert direction.get_attribute("aria-label") == "Сначала новые"
    assert direction.inner_text() in ("↓", "↑")
    meta = card.locator(".quiz-card-meta")
    assert meta.locator(":scope > *").first.get_attribute("class") == "quiz-card-difficulty"
    assert card.locator(".quiz-card-difficulty").inner_text() == "Сложность: низкая"
    assert card.locator(".quiz-tags").inner_text().splitlines() == ["Масти", "Картинки"]
    assert page.evaluate("element => getComputedStyle(element).fontSize", card.locator(".quiz-card-description").element_handle()) == "19px"
    difficulty_box = card.locator(".quiz-card-difficulty").bounding_box()
    tags_box = card.locator(".quiz-tags").bounding_box()
    assert abs((difficulty_box["y"] + difficulty_box["height"]) - (tags_box["y"] + tags_box["height"])) <= 2
    cover = card.locator(".quiz-cover")
    image = cover.locator("img")
    card_box = card.bounding_box()
    cover_box = cover.bounding_box()
    assert round(cover_box["width"]) == 220
    assert abs(cover_box["height"] - card_box["height"]) <= 2
    assert page.evaluate("element => getComputedStyle(element).objectFit", image.element_handle()) == "cover"
    assert page.evaluate("element => getComputedStyle(element).objectPosition", image.element_handle()) == "100% 50%"
    page.set_viewport_size({"width": 701, "height": 900})
    assert page.evaluate("element => getComputedStyle(element).gridTemplateColumns.split(' ').length", card.element_handle()) == 2
    page.set_viewport_size({"width": 700, "height": 900})
    assert page.evaluate("element => getComputedStyle(element).gridTemplateColumns.split(' ').length", card.element_handle()) == 1
    cover_box = cover.bounding_box()
    assert abs(cover_box["width"] - cover_box["height"]) <= 2
    assert page.evaluate("element => getComputedStyle(element).objectPosition", image.element_handle()) == "50% 50%"
    for width in (1440, 375):
        page.set_viewport_size({"width": width, "height": 900})
        assert not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert page.evaluate("element => getComputedStyle(element).fontSize", card.locator(".quiz-card-description").element_handle()) == "17.4px"
    page.get_by_role("button", name="Масти", exact=True).first.click()
    assert "tag=horses" in page.url
    criterion.select_option("difficulty")
    assert criterion.input_value() == "difficulty"
    assert direction.inner_text() == "↓"
    assert direction.get_attribute("title") == "Сначала лёгкие"
    assert "tag=horses" in page.url and "page=1" in page.url and "direction=down" in page.url
    direction.click()
    assert direction.inner_text() == "↑"
    assert direction.get_attribute("title") == "Сначала сложные"
    criterion.select_option("title")
    assert direction.inner_text() == "↓"
    assert direction.get_attribute("title") == "От А до Я"
    assert "tag=horses" in page.url


def main():
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    server = subprocess.Popen(
        ["python", "-m", "http.server", "8766", "-d", "_site", "--bind", "127.0.0.1"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        draft = {**QUIZ, "slug": "ui-draft", "title": "Тестовый черновик", "published": False}
        DRAFT_PATH.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        BROKEN_PATH.write_text('{"slug": "ui-broken",', encoding="utf-8")
        time.sleep(1)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE), headless=True,
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                args=["--disable-crash-reporter", "--disable-breakpad"],
            )
            javascript_errors = []
            page = context.pages[0]
            page.on("pageerror", lambda error: javascript_errors.append(str(error)))
            context.on("page", lambda opened_page: opened_page.on("pageerror", lambda error: javascript_errors.append(str(error))))
            page.goto(f"{BASE_URL}/quiz.html")
            page.get_by_text("Не указана викторина для открытия.").wait_for()
            page.goto(f"{BASE_URL}/quiz.html?quiz=unknown-quiz")
            page.get_by_text("Викторина не найдена.").wait_for()
            page.goto(f"{BASE_URL}/quiz.html?quiz=ui-broken")
            page.get_by_text("Не удалось загрузить викторину. Попробуйте позже.").wait_for()
            page.goto(f"{BASE_URL}/quiz.html?quiz=ui-draft")
            page.get_by_text("Эта викторина пока не опубликована.").wait_for()
            page.goto(f"{BASE_URL}/quiz.html?quiz=ui-draft&preview=1")
            page.get_by_text("Предварительный просмотр. Викторина не опубликована.").wait_for()
            page.get_by_role("button", name="Начать викторину").wait_for()
            catalog_card_checks(page)
            share_page_url = f"{BASE_URL}/v/anatomy/"
            page.goto(f"{BASE_URL}/quizzes.html")
            anatomy_card = page.locator('.quiz-card:has(.quiz-card-link[href="/v/anatomy/"])')
            anatomy_card.wait_for()
            assert anatomy_card.locator(".quiz-card-link").count() == 1
            assert anatomy_card.locator("h3 a, .quiz-cover a").count() == 0
            anatomy_card.locator(".quiz-card-link").click()
            page.get_by_role("heading", name="Анатомия лошади").wait_for()
            assert page.url == share_page_url
            assert page.title() == "Анатомия лошади — Викторины о лошадках"
            assert page.locator('link[rel="canonical"]').get_attribute("href") == "https://tssrkt.github.io/quiz/v/anatomy/"
            assert page.locator('meta[property="og:image"]').get_attribute("content") == "https://tssrkt.github.io/quiz/img/covers/anatomy.webp"
            all_correct(page)
            all_wrong(page)
            page = mixed_with_reload(context, page)
            adaptive_checks(page)
            assert not javascript_errors, f"Ошибки JavaScript: {javascript_errors}"
            context.close()
        print("ui_quiz_scenarios.py: 3 браузерных сценария пройдены")
    finally:
        server.terminate()
        server.wait(timeout=5)
        if PROFILE.exists():
            shutil.rmtree(PROFILE, ignore_errors=True)
        DRAFT_PATH.unlink(missing_ok=True)
        BROKEN_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
