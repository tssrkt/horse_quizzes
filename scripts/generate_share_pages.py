#!/usr/bin/env python3
"""Generate full quiz pages with individual social metadata."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

try:
    from site_config import load_site_config
except ModuleNotFoundError:  # Imported as scripts.generate_share_pages by tests/tools.
    from scripts.site_config import load_site_config

ROOT = Path(__file__).resolve().parents[1]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_FIELDS = ("slug", "title", "short_description", "cover")


class SharePageError(Exception):
    pass


def load_published_quizzes(root: Path) -> list[dict]:
    quizzes = []
    errors = []
    paths = (list((root / "data" / "quizzes").glob("*.json")) +
             list((root / "data" / "vocabulary-quizzes").glob("*.json")) +
             list((root / "data" / "english-quizzes").glob("*.json")))
    for path in sorted(paths):
        try:
            quiz = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: некорректный JSON: {error}")
            continue
        if quiz.get("published") is not True:
            continue
        label = path.relative_to(root)
        for field in REQUIRED_FIELDS:
            value = quiz.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}.{field}: для опубликованной викторины требуется непустая строка")
        slug = quiz.get("slug", "")
        if isinstance(slug, str) and (not SLUG_RE.fullmatch(slug) or path.stem != slug):
            errors.append(f"{label}.slug: некорректный slug или он не совпадает с именем файла")
        cover = quiz.get("cover", "")
        if isinstance(cover, str) and cover.strip():
            cover_path = root / Path(cover)
            if cover.startswith(("http://", "https://")) or not cover_path.is_file():
                errors.append(f"{label}.cover: требуется существующий локальный файл обложки")
        quizzes.append(quiz)
    if errors:
        raise SharePageError("\n".join(errors))
    return quizzes


def render_page(quiz: dict, template: str | None = None, public_url: str | None = None, locale: str = "ru") -> str:
    public_url = public_url or load_site_config(ROOT)["public_url"]
    english = locale == "en"
    public_slug = quiz["source_quiz"] if english else quiz["slug"]
    slug = quote(public_slug, safe="-")
    title = html.escape(quiz["title"].strip(), quote=True)
    description = html.escape(quiz["short_description"].strip(), quote=True)
    share_url = f"{public_url}{'en/' if english else ''}v/{slug}/"
    alternate_slug = quiz.get("_english_public_slug")
    alternate_url = f"{public_url}v/{slug}/" if english else (f"{public_url}en/v/{quote(alternate_slug, safe='-')}/" if alternate_slug else "")
    cover_url_path = quiz["cover"].replace("\\", "/")
    image_url = f"{public_url}{quote(cover_url_path, safe='/-.')}"
    image_alt = html.escape((f"Quiz cover: {quiz['title'].strip()}" if english else f"Обложка викторины «{quiz['title'].strip()}»"), quote=True)
    site_name = "Horse Quizzes" if english else "Викторины о лошадках"
    title_suffix = "Английский для конников" if quiz.get("type") == "vocabulary" else site_name
    page_title = f"{title} — {title_suffix}"
    metadata = f'''<meta name="description" content="{description}">
  <title>{page_title}</title>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{site_name}">
  <meta property="og:locale" content="{'en_US' if english else 'ru_RU'}">
  <meta property="og:locale:alternate" content="{'ru_RU' if english else 'en_US'}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{share_url}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:alt" content="{image_alt}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{image_url}">
  <link rel="canonical" href="{share_url}">''' + (f'''
  <link rel="alternate" hreflang="ru" href="{alternate_url if english else share_url}">
  <link rel="alternate" hreflang="en" href="{share_url if english else alternate_url}">
  <link rel="alternate" hreflang="x-default" href="{alternate_url if english else share_url}">''' if english or alternate_url else "")
    template = template if template is not None else (ROOT / ("en/quiz.html" if english else "quiz.html")).read_text(encoding="utf-8")
    page, replacements = re.subn(
        r'(?:<meta name="robots" content="noindex,follow">)?<meta name="description" content="[^"]*"><title>[^<]*</title>',
        metadata,
        template,
        count=1,
    )
    if replacements != 1:
        raise SharePageError("quiz.html: не найден стандартный блок description/title")
    if not english:
        page = re.sub(
            r'(?P<attribute>href|src)="(?P<path>(?!https?://|#|/)[^"]+)"',
            lambda match: f'{match.group("attribute")}="../../{match.group("path")}"', page,
        )
        page = page.replace('{{SITE_PATH}}', '../../')
        en_href = f"../../en/v/{quote(alternate_slug, safe='-')}/" if alternate_slug else "../../en/quizzes.html"
        en_label = "English version" if alternate_slug else "Английская версия этой викторины пока недоступна"
        switch = f'<nav class="language-switch" aria-label="Выбор языка"><a href="./" aria-current="page">RU</a><span aria-hidden="true">|</span><a href="{en_href}" lang="en" title="{en_label}">EN</a></nav>'
        page = page.replace('<button class="menu-toggle"', switch + '<button class="menu-toggle"', 1)
    else:
        page = page.replace('data-language-ru href="../../../quizzes.html"', f'data-language-ru href="../../../v/{slug}/"')
    return page


def generate(root: Path = ROOT, output: Path | None = None, english_output: Path | None = None) -> int:
    output = output or root / "v"
    quizzes = load_published_quizzes(root)
    public_url = load_site_config(root)["public_url"]
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    template = (root / "quiz.html").read_text(encoding="utf-8")
    english_output = english_output or output.parent / "en" / "v"
    if english_output.exists():
        shutil.rmtree(english_output)
    english_output.mkdir(parents=True)
    english_template = (root / "en" / "quiz.html").read_text(encoding="utf-8")
    published_english = {quiz["source_quiz"] for quiz in quizzes if quiz.get("type") == "english"}
    for quiz in quizzes:
        if quiz.get("type") == "english":
            directory = english_output / quiz["source_quiz"]
            directory.mkdir()
            (directory / "index.html").write_text(render_page(quiz, english_template, public_url, "en"), encoding="utf-8", newline="\n")
        elif quiz.get("slug") in published_english:
            quiz = {**quiz, "_english_public_slug": quiz["slug"]}
        directory = output / quiz["slug"]
        directory.mkdir()
        (directory / "index.html").write_text(render_page(quiz, template, public_url), encoding="utf-8", newline="\n")
    return len(quizzes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Сгенерировать страницы превью опубликованных викторин")
    parser.add_argument("--output", type=Path, default=ROOT / "v", help="каталог назначения")
    args = parser.parse_args()
    try:
        count = generate(ROOT, args.output)
    except SharePageError as error:
        print(f"Ошибка генерации страниц превью:\n{error}", file=sys.stderr)
        return 1
    print(f"Создано страниц превью: {count}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
