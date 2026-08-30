"""Optional desktop/mobile smoke test for the generated bilingual site."""

import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8767"


def run():
    server = subprocess.Popen(["python", "-m", "http.server", "8767", "--directory", str(ROOT / "_site")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(f"{BASE}/en/")
            assert page.locator("html").get_attribute("lang") == "en"
            assert page.get_by_role("link", name="EN", exact=True).is_visible()
            page.get_by_role("link", name="Quizzes", exact=True).first.click()
            page.locator(".quiz-card").first.wait_for()
            assert page.locator(".catalog-tabs").count() == 0
            assert page.get_by_text("Английский для конников").count() == 0
            first_href = page.locator(".quiz-card-link").first.get_attribute("href")
            assert "/en/v/" in first_href and not first_href.rstrip("/").endswith("-en")
            page.locator(".quiz-card-link").first.click()
            page.get_by_role("button", name="Start quiz").wait_for()
            assert page.get_by_role("link", name="RU", exact=True).get_attribute("href").startswith("../../../v/")
            page.get_by_role("button", name="Start quiz").click()
            page.get_by_text("Question 1 of", exact=False).wait_for()
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(f"{BASE}/en/")
            assert mobile.get_by_role("navigation", name="Language").is_visible()
            assert mobile.get_by_role("button", name="Open menu").is_visible()
            assert mobile.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
            mobile.get_by_role("button", name="Open menu").click()
            assert mobile.get_by_role("button", name="Close menu").get_attribute("aria-expanded") == "true"
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    run()
    print("ui_bilingual_smoke: passed")
