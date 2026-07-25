#!/usr/bin/env python3
"""Generate static Open Graph redirect pages for published quizzes."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = "https://tssrkt.github.io/quiz"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_FIELDS = ("slug", "title", "short_description", "cover")


class SharePageError(Exception):
    pass


def load_published_quizzes(root: Path) -> list[dict]:
    quizzes = []
    errors = []
    for path in sorted((root / "data" / "quizzes").glob("*.json")):
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


def render_page(quiz: dict) -> str:
    slug = quote(quiz["slug"], safe="-")
    title = html.escape(quiz["title"].strip(), quote=True)
    description = html.escape(quiz["short_description"].strip(), quote=True)
    share_url = f"{PUBLIC_ROOT}/v/{slug}/"
    quiz_url = f"{PUBLIC_ROOT}/quiz.html?quiz={slug}"
    cover_url_path = quiz["cover"].replace("\\", "/")
    image_url = f"{PUBLIC_ROOT}/{quote(cover_url_path, safe='/-.')}"
    image_alt = html.escape(f"Обложка викторины «{quiz['title'].strip()}»", quote=True)
    script_url = json.dumps(quiz_url, ensure_ascii=False).replace("<", "\\u003c")
    return f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Викторины о лошадках</title>
  <meta name="description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Викторины о лошадках">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{share_url}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:alt" content="{image_alt}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{image_url}">
  <link rel="canonical" href="{quiz_url}">
  <meta http-equiv="refresh" content="0; url={quiz_url}">
  <script>window.location.replace({script_url});</script>
</head>
<body>
  <p>Переход к викторине: <a href="{quiz_url}">{title}</a>.</p>
</body>
</html>
'''


def generate(root: Path = ROOT, output: Path | None = None) -> int:
    output = output or root / "v"
    quizzes = load_published_quizzes(root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for quiz in quizzes:
        directory = output / quiz["slug"]
        directory.mkdir()
        (directory / "index.html").write_text(render_page(quiz), encoding="utf-8", newline="\n")
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
