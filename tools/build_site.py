#!/usr/bin/env python3
"""Validate content and build the static site into _site/ (stdlib only)."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_site"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
QUESTION_ID_RE = re.compile(r"^question-\d{2,}$")
PUBLICATION_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")
ANSWER_ID_RE = re.compile(r"^answer-\d{2,}$")
DIFFICULTIES = {"low", "medium", "high"}
HTML_FILES = ("index.html", "quizzes.html", "quiz.html", "contacts.html", "404.html")
ROOT_FILES = ("favicon.ico",)
COPY_DIRS = ("css", "js")


class ContentError(Exception):
    pass


def read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ContentError(f"{path.relative_to(ROOT)}: некорректный JSON: {error}") from None
    if not isinstance(value, dict):
        raise ContentError(f"{path.relative_to(ROOT)}: корневое значение должно быть объектом")
    return value


def require_string(data: dict, field: str, label: str, errors: list[str], allow_empty: bool = False) -> str:
    value = data.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        errors.append(f"{label}.{field}: требуется непустая строка" if not allow_empty else f"{label}.{field}: требуется строка")
        return ""
    return value.strip()


def validate_slug(value: str, label: str, errors: list[str]) -> None:
    if value and not SLUG_RE.fullmatch(value):
        errors.append(f"{label}: допустимы строчные латинские буквы, цифры и одиночные дефисы")


def validate_local_image(value: object, prefix: str, label: str, errors: list[str]) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        errors.append(f"{label}: путь должен быть строкой")
        return
    if value.startswith(("/", "\\")) or "\\" in value or ".." in Path(value).parts:
        errors.append(f"{label}: требуется безопасный относительный путь без начального /")
        return
    if not value.startswith(prefix):
        errors.append(f"{label}: путь должен начинаться с {prefix}")
        return
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"{label}: путь выходит за пределы проекта")
        return
    if not candidate.is_file():
        errors.append(f"{label}: файл не найден: {value}")


def validate_external_url(value: object, label: str, errors: list[str]) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        errors.append(f"{label}: ссылка должна быть строкой")
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{label}: требуется полный адрес http:// или https://")


def load_tags(data_root: Path) -> tuple[list[dict], dict[str, dict]]:
    errors: list[str] = []
    tags: list[dict] = []
    slugs: dict[str, Path] = {}
    names: dict[str, Path] = {}
    for path in sorted((data_root / "tags").glob("*.json")):
        data = read_json(path)
        label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        name = require_string(data, "name", label, errors)
        slug = require_string(data, "slug", label, errors)
        validate_slug(slug, f"{label}.slug", errors)
        if slug and path.stem != slug:
            errors.append(f"{label}.slug: должен совпадать с именем файла «{path.stem}»")
        if slug in slugs:
            errors.append(f"{label}.slug: повторяет slug из {slugs[slug].name}")
        elif slug:
            slugs[slug] = path
        folded = name.casefold()
        if folded in names:
            errors.append(f"{label}.name: название повторяет {names[folded].name} без учёта регистра")
        elif name:
            names[folded] = path
        if not isinstance(data.get("published"), bool):
            errors.append(f"{label}.published: требуется true или false")
        tags.append(data)
    if errors:
        raise ContentError("\n".join(errors))
    return tags, {tag["slug"]: tag for tag in tags}


def load_quizzes(data_root: Path, known_tags: dict[str, dict]) -> list[dict]:
    errors: list[str] = []
    quizzes: list[dict] = []
    slugs: dict[str, Path] = {}
    for path in sorted((data_root / "quizzes").glob("*.json")):
        data = read_json(path)
        label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        slug = require_string(data, "slug", label, errors)
        validate_slug(slug, f"{label}.slug", errors)
        if slug and path.stem != slug:
            errors.append(f"{label}.slug: должен совпадать с именем файла «{path.stem}»")
        if slug in slugs:
            errors.append(f"{label}.slug: повторяет slug из {slugs[slug].name}")
        elif slug:
            slugs[slug] = path
        for field in ("title", "short_description", "intro"):
            require_string(data, field, label, errors)
        if not isinstance(data.get("published"), bool):
            errors.append(f"{label}.published: требуется true или false")
        difficulty = data.get("difficulty")
        if difficulty not in DIFFICULTIES:
            errors.append(f"{label}.difficulty: требуется одно из значений low, medium, high")
        publication_date = require_string(data, "publication_date", label, errors)
        if publication_date:
            try:
                if PUBLICATION_DATETIME_RE.fullmatch(publication_date):
                    publication_datetime = dt.datetime.fromisoformat(publication_date.replace("Z", "+00:00"))
                    if publication_datetime.tzinfo is None or publication_datetime.utcoffset() is None:
                        raise ValueError
                elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_date):
                    dt.date.fromisoformat(publication_date)
                else:
                    raise ValueError
            except ValueError:
                errors.append(
                    f"{label}.publication_date: требуется дата YYYY-MM-DD либо ISO 8601 "
                    "с секундами и часовым поясом"
                )
        tags = data.get("tags")
        if not isinstance(tags, list) or not tags or any(not isinstance(tag, str) or not tag for tag in tags):
            errors.append(f"{label}.tags: требуется непустой массив slug тегов")
        else:
            for tag in tags:
                if tag not in known_tags:
                    errors.append(f"{label}.tags: неизвестный тег «{tag}»")
        next_quiz = data.get("next_quiz")
        if next_quiz not in (None, ""):
            if not isinstance(next_quiz, str):
                errors.append(f"{label}.next_quiz: требуется slug викторины")
            else:
                validate_slug(next_quiz, f"{label}.next_quiz", errors)
        validate_local_image(data.get("cover", ""), "img/covers/", f"{label}.cover", errors)
        questions = data.get("questions")
        if not isinstance(questions, list) or not questions:
            errors.append(f"{label}.questions: требуется непустой массив")
            questions = []
        question_ids: dict[str, int] = {}
        for q_index, question in enumerate(questions, 1):
            qlabel = f"{label}.questions[{q_index}]"
            if not isinstance(question, dict):
                errors.append(f"{qlabel}: требуется объект")
                continue
            question_id = require_string(question, "id", qlabel, errors)
            if question_id and not QUESTION_ID_RE.fullmatch(question_id):
                errors.append(f"{qlabel}.id: требуется формат question-N с минимум двумя цифрами")
            if question_id in question_ids:
                errors.append(
                    f"{label}: конфликтующий ID вопроса «{question_id}» в questions[{question_ids[question_id]}] и questions[{q_index}]"
                )
            elif question_id:
                question_ids[question_id] = q_index
            require_string(question, "question", qlabel, errors)
            require_string(question, "explanation", qlabel, errors)
            image = question.get("image", "")
            validate_local_image(image, "img/quiz/", f"{qlabel}.image", errors)
            if isinstance(image, str) and image:
                image_parts = Path(image).parts
                if len(image_parts) > 3 and image_parts[:2] == ("img", "quiz") and image_parts[2] != slug:
                    errors.append(f"{qlabel}.image: папка изображения должна совпадать со slug «{slug}»")
            if "image_alt" in question and not isinstance(question["image_alt"], str):
                errors.append(f"{qlabel}.image_alt: для изображения требуется строка")
            validate_external_url(question.get("image_source_url", ""), f"{qlabel}.image_source_url", errors)
            answers = question.get("answers")
            if not isinstance(answers, list) or not 2 <= len(answers) <= 6:
                errors.append(f"{qlabel}.answers: требуется от 2 до 6 вариантов")
                answers = []
            answer_ids: dict[str, int] = {}
            legacy_correct_ids = []
            for a_index, answer in enumerate(answers, 1):
                alabel = f"{qlabel}.answers[{a_index}]"
                if not isinstance(answer, dict):
                    errors.append(f"{alabel}: требуется объект")
                    continue
                answer_id = require_string(answer, "id", alabel, errors)
                if answer_id and not ANSWER_ID_RE.fullmatch(answer_id):
                    errors.append(f"{alabel}.id: требуется формат answer-N с минимум двумя цифрами")
                if answer_id in answer_ids:
                    errors.append(
                        f"{label}: конфликтующий ID ответа «{answer_id}» в questions[{q_index}].answers[{answer_ids[answer_id]}] и questions[{q_index}].answers[{a_index}]"
                    )
                elif answer_id:
                    answer_ids[answer_id] = a_index
                require_string(answer, "text", alabel, errors)
                if "correct" in answer:
                    if not isinstance(answer["correct"], bool):
                        errors.append(f"{alabel}.correct: требуется true или false")
                    elif answer["correct"]:
                        legacy_correct_ids.append(answer_id)
            correct_answer_id = question.get("correct_answer_id")
            if correct_answer_id is None:
                if len(legacy_correct_ids) != 1:
                    errors.append(f"{qlabel}: требуется correct_answer_id или ровно один старый correct: true")
                elif legacy_correct_ids[0]:
                    question["correct_answer_id"] = legacy_correct_ids[0]
            elif not isinstance(correct_answer_id, str) or not correct_answer_id.strip():
                errors.append(f"{qlabel}.correct_answer_id: требуется непустой ID варианта")
            elif correct_answer_id not in answer_ids:
                errors.append(f"{qlabel}.correct_answer_id: вариант «{correct_answer_id}» отсутствует в answers")
            if correct_answer_id is not None and legacy_correct_ids and legacy_correct_ids != [correct_answer_id]:
                errors.append(f"{qlabel}: correct_answer_id противоречит старому correct: true")
        quizzes.append(data)
    quiz_by_slug = {quiz.get("slug"): quiz for quiz in quizzes}
    for quiz in quizzes:
        next_slug = quiz.get("next_quiz")
        if not next_slug or not isinstance(next_slug, str):
            continue
        target = quiz_by_slug.get(next_slug)
        if target is None:
            errors.append(f"{quiz.get('slug', 'викторина')}.next_quiz: неизвестная викторина «{next_slug}»")
        elif quiz.get("published") and not target.get("published"):
            errors.append(f"{quiz['slug']}.next_quiz: опубликованная викторина не может ссылаться на неопубликованную «{next_slug}»")
    if errors:
        raise ContentError("\n".join(errors))
    return [normalize_quiz(quiz) for quiz in quizzes]


def normalize_quiz(source: dict) -> dict:
    quiz = copy.deepcopy(source)
    slug = quiz["slug"]
    for q_index, question in enumerate(quiz["questions"], 1):
        for answer in question["answers"]:
            answer.pop("correct", None)
        image = question.get("image", "")
        if image:
            question["_source_image"] = image
            question["image"] = f"img/quiz/{slug}/{q_index:02d}{Path(image).suffix.lower()}"
    version_quiz = copy.deepcopy(quiz)
    image_hashes = []
    for question in version_quiz["questions"]:
        source_image = question.pop("_source_image", None)
        image_hashes.append(hashlib.sha256((ROOT / source_image).read_bytes()).hexdigest() if source_image else "")
    version_payload = {"quiz": version_quiz, "question_image_sha256": image_hashes}
    version_data = json.dumps(version_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    quiz["content_version"] = hashlib.sha256(version_data).hexdigest()
    return quiz


def make_catalog(tags: list[dict], quizzes: list[dict]) -> dict:
    published_tags = sorted(
        ({"slug": tag["slug"], "name": tag["name"]} for tag in tags if tag["published"]),
        key=lambda tag: tag["name"].casefold(),
    )
    published_quizzes = [
        {
            "slug": quiz["slug"],
            "title": quiz["title"],
            "published": True,
            "publication_date": quiz["publication_date"],
            "short_description": quiz["short_description"],
            "difficulty": quiz["difficulty"],
            "cover": quiz.get("cover", ""),
            "tags": quiz["tags"],
            "question_count": len(quiz["questions"]),
            "content_version": quiz["content_version"],
        }
        for quiz in quizzes if quiz["published"]
    ]
    return {"tags": list(published_tags), "quizzes": published_quizzes}


def build(output: Path = OUTPUT) -> dict:
    tags, known_tags = load_tags(ROOT / "data")
    quizzes = load_quizzes(ROOT / "data", known_tags)
    catalog = make_catalog(tags, quizzes)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for filename in HTML_FILES:
        shutil.copy2(ROOT / filename, output / filename)
    for filename in ROOT_FILES:
        shutil.copy2(ROOT / filename, output / filename)
    for dirname in COPY_DIRS:
        shutil.copytree(ROOT / dirname, output / dirname, ignore=shutil.ignore_patterns(".gitkeep"))
    shutil.copytree(ROOT / "img" / "covers", output / "img" / "covers", ignore=shutil.ignore_patterns(".gitkeep"))
    shutil.copytree(
        ROOT / "img" / "icons",
        output / "img" / "icons",
        ignore=shutil.ignore_patterns(".gitkeep"),
    )
    shutil.copytree(ROOT / "data" / "tags", output / "data" / "tags")
    quiz_output = output / "data" / "quizzes"
    quiz_output.mkdir(parents=True)
    for quiz in quizzes:
        for question in quiz["questions"]:
            source_image = question.pop("_source_image", "")
            if source_image:
                destination = output / question["image"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / source_image, destination)
        with (quiz_output / f"{quiz['slug']}.json").open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(quiz, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    with (output / "data" / "catalog.json").open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(catalog, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверить контент и собрать статический сайт")
    parser.add_argument("--check", action="store_true", help="только проверить данные, не создавать _site")
    args = parser.parse_args()
    try:
        tags, known_tags = load_tags(ROOT / "data")
        quizzes = load_quizzes(ROOT / "data", known_tags)
        if args.check:
            print(f"Проверка пройдена: тегов — {len(tags)}, викторин — {len(quizzes)}.")
        else:
            catalog = build()
            print(f"Сборка готова: {OUTPUT.relative_to(ROOT)}; опубликованных викторин — {len(catalog['quizzes'])}.")
        return 0
    except ContentError as error:
        print("Ошибка проверки контента:", file=sys.stderr)
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
