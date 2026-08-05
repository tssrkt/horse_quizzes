#!/usr/bin/env python3
"""Validate content and build the static site into _site/ (stdlib only)."""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_share_pages import SharePageError, generate as generate_share_pages

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
VOCABULARY_TYPE = "vocabulary"


class ContentError(Exception):
    pass


def _xlsx_rows(path: Path) -> list[list[str]]:
    """Read the first worksheet of an xlsx file without a third-party dependency."""
    try:
        with zipfile.ZipFile(path) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")) for item in root]
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel_targets = {node.attrib["Id"]: node.attrib["Target"] for node in relations}
            sheet = next(node for node in workbook.iter() if node.tag.endswith("}sheet"))
            rel_id = next(value for key, value in sheet.attrib.items() if key.endswith("}id"))
            target = rel_targets[rel_id].lstrip("/")
            sheet_name = target if target.startswith("xl/") else f"xl/{target}"
            root = ET.fromstring(archive.read(sheet_name))
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration, ET.ParseError, IndexError) as error:
        raise ContentError(f"{path.relative_to(ROOT)}: файл Excel не читается: {error}") from None
    rows = []
    for row in (node for node in root.iter() if node.tag.endswith("}row")):
        values: dict[int, str] = {}
        for cell in (node for node in row if node.tag.endswith("}c")):
            reference = cell.attrib.get("r", "A1")
            letters = re.match(r"[A-Z]+", reference).group(0)
            column = 0
            for letter in letters:
                column = column * 26 + ord(letter) - 64
            value_node = next((node for node in cell.iter() if node.tag.endswith("}v")), None)
            inline = "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t"))
            raw = value_node.text if value_node is not None and value_node.text is not None else inline
            if cell.attrib.get("t") == "s" and raw:
                raw = shared[int(raw)]
            values[column - 1] = raw or ""
        rows.append([values.get(index, "") for index in range(max(values, default=-1) + 1)])
    return rows


def import_vocabulary_table(path: Path) -> list[dict]:
    try:
        if path.suffix.lower() == ".xlsx":
            rows = _xlsx_rows(path)
        elif path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
        else:
            raise ContentError(f"{path.relative_to(ROOT)}: поддерживаются таблицы .xlsx и .csv")
    except ContentError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise ContentError(f"{path.relative_to(ROOT)}: файл таблицы не читается: {error}") from None
    if not rows:
        raise ContentError(f"{path.relative_to(ROOT)}: после обработки не осталось валидных слов")
    headers = {str(value).strip(): index for index, value in enumerate(rows[0])}
    missing = [name for name in ("English", "Russian") if name not in headers]
    if missing:
        raise ContentError(f"{path.relative_to(ROOT)}: отсутствуют обязательные столбцы: {', '.join(missing)}")
    words, errors = [], []
    for row_number, row in enumerate(rows[1:], 2):
        get = lambda name: str(row[headers[name]] if headers[name] < len(row) else "").strip()
        english, russian = get("English"), get("Russian")
        category = get("Category") if "Category" in headers else ""
        if not english and not russian and not category:
            continue
        if not english or not russian:
            errors.append(f"{path.relative_to(ROOT)}: строка {row_number}: English и Russian обязательны")
            continue
        words.append({"english": english, "russian": russian, "category": category})
    if not words and not errors:
        errors.append(f"{path.relative_to(ROOT)}: после обработки не осталось валидных слов")
    groups: dict[str, int] = {}
    for word in words:
        groups[word["category"]] = groups.get(word["category"], 0) + 1
    for category, count in groups.items():
        if count < 2:
            errors.append(f"{path.relative_to(ROOT)}: категория «{category or '(пустая)'}» содержит меньше двух строк")
    if errors:
        raise ContentError("\n".join(errors))
    return words


def validate_embedded_vocabulary(words: object, label: str) -> list[dict]:
    if not isinstance(words, list) or not words:
        raise ContentError(f"{label}: встроенный словарь должен быть непустым массивом")
    normalized = []
    errors = []
    for index, word in enumerate(words, 1):
        if not isinstance(word, dict):
            errors.append(f"{label}[{index}]: требуется объект")
            continue
        english = word.get("english")
        russian = word.get("russian")
        category = word.get("category", "")
        if not isinstance(english, str) or not english.strip() or not isinstance(russian, str) or not russian.strip():
            errors.append(f"{label}[{index}]: English и Russian обязательны")
            continue
        if not isinstance(category, str):
            errors.append(f"{label}[{index}].category: требуется строка")
            continue
        normalized.append({"english": english.strip(), "russian": russian.strip(), "category": category.strip()})
    groups: dict[str, int] = {}
    for word in normalized:
        groups[word["category"]] = groups.get(word["category"], 0) + 1
    for category, count in groups.items():
        if count < 2:
            errors.append(f"{label}: категория «{category or '(пустая)'}» содержит меньше двух строк")
    if errors:
        raise ContentError("\n".join(errors))
    return normalized


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
    quiz_sources: dict[str, tuple[str, str]] = {}
    quiz_paths = list((data_root / "quizzes").glob("*.json")) + list((data_root / "vocabulary-quizzes").glob("*.json"))
    for path in sorted(quiz_paths):
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
        if "questionImagesAlt" in data and not isinstance(data["questionImagesAlt"], str):
            errors.append(f"{label}.questionImagesAlt: требуется строка")
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
        validate_local_image(data.get("cover", ""), "img/covers/", f"{label}.cover", errors)
        quiz_type = data.get("type", "quiz")
        if quiz_type not in {"quiz", VOCABULARY_TYPE}:
            errors.append(f"{label}.type: требуется quiz или vocabulary")
        actual_type = VOCABULARY_TYPE if path.parent.name == "vocabulary-quizzes" else "quiz"
        if slug:
            quiz_sources[slug] = (label, actual_type)
        relation_field = "previous_quiz"
        relation_slug = data.get(relation_field)
        if relation_slug not in (None, ""):
            if not isinstance(relation_slug, str):
                errors.append(f"{label}.{relation_field}: требуется slug викторины")
            else:
                validate_slug(relation_slug, f"{label}.{relation_field}", errors)
        if "next_quiz" in data:
            errors.append(f"{label}.next_quiz: устаревшее ручное поле; используйте previous_quiz")
        if quiz_type == VOCABULARY_TYPE:
            source_parts = data.get("parts")
            if source_parts is None:
                source_parts = [{"title": "", "table": data.get("table")}]
            elif not isinstance(source_parts, list) or not source_parts:
                errors.append(f"{label}.parts: требуется хотя бы одна часть словаря")
                source_parts = []
            built_parts = []
            for part_index, part in enumerate(source_parts, 1):
                part_label = f"{label}.parts[{part_index}]"
                if not isinstance(part, dict):
                    errors.append(f"{part_label}: требуется объект")
                    continue
                title = part.get("title", "")
                if not isinstance(title, str):
                    errors.append(f"{part_label}.title: требуется строка")
                    title = ""
                title = title.strip() or f"Часть {part_index}"
                table = part.get("table", "")
                if not isinstance(table, str):
                    errors.append(f"{part_label}.table: требуется строка")
                    table = ""
                words = []
                table_path = (path.parent / table).resolve() if table else None
                embedded = part.get("vocabulary")
                if table_path and table_path.exists():
                    try:
                        table_path.relative_to(ROOT.resolve())
                    except ValueError:
                        errors.append(f"{part_label} «{title}», таблица {table}: путь выходит за пределы проекта")
                    else:
                        try:
                            words = import_vocabulary_table(table_path)
                        except ContentError as error:
                            errors.append(f"{part_label} «{title}», таблица {table}: {error}")
                elif embedded is not None:
                    try:
                        words = validate_embedded_vocabulary(embedded, f"{part_label}.vocabulary")
                    except ContentError as error:
                        errors.append(str(error))
                elif table_path:
                    errors.append(f"{part_label} «{title}», таблица {table}: файл не найден и встроенные данные отсутствуют")
                else:
                    errors.append(f"{part_label} «{title}»: требуется таблица или встроенный словарь")
                part_id = part.get("id")
                if not isinstance(part_id, str) or not SLUG_RE.fullmatch(part_id):
                    identity = table or json.dumps(words, ensure_ascii=False, sort_keys=True)
                    part_id = "part-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
                built_parts.append({"id": part_id, "title": title, "word_count": len(words), "vocabulary": words})
            if len({part["id"] for part in built_parts}) != len(built_parts):
                errors.append(f"{label}.parts: идентификаторы частей должны быть уникальными")
            data["parts"] = built_parts
            data["vocabulary"] = [word for part in built_parts for word in part["vocabulary"]]
            data["word_count"] = len(data["vocabulary"])
            # Reuse the mature question validator on transient questions. They are
            # removed again by normalize_quiz and never enter source or output.
            data["questions"] = []
            question_index = 0
            for built_part in built_parts:
                groups = {}
                for word in built_part["vocabulary"]:
                    groups.setdefault(word["category"], []).append(word)
                for word in built_part["vocabulary"]:
                    question_index += 1
                    choices = groups[word["category"]][:6]
                    if word not in choices:
                        choices[-1] = word
                    data["questions"].append({
                        "id": f"question-{question_index:02d}", "question": word["english"], "explanation": word["russian"],
                        "answers": [{"id": f"answer-{answer_index:02d}", "text": choice["russian"]} for answer_index, choice in enumerate(choices, 1)],
                        "correct_answer_id": f"answer-{choices.index(word) + 1:02d}",
                    })
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
    computed_next: dict[str, str] = {}
    for quiz in quizzes:
        current_slug = quiz.get("slug")
        current_label, current_type = quiz_sources.get(current_slug, (str(current_slug), "quiz"))
        previous_slug = quiz.get("previous_quiz")
        if not previous_slug or not isinstance(previous_slug, str):
            continue
        target = quiz_by_slug.get(previous_slug)
        target_source = quiz_sources.get(previous_slug)
        if previous_slug == current_slug:
            errors.append(f"{current_label}.previous_quiz: проблемный slug «{previous_slug}»: самоссылка запрещена")
        elif target is None:
            errors.append(f"{current_label}.previous_quiz: проблемный slug «{previous_slug}»: викторина не найдена")
        elif target_source and target_source[1] != current_type:
            errors.append(
                f"{current_label}.previous_quiz: проблемный slug «{previous_slug}»: цель имеет тип "
                f"«{target_source[1]}», ожидался тип «{current_type}»"
            )
        elif previous_slug in computed_next:
            errors.append(
                f"{current_label}.previous_quiz: проблемный slug «{previous_slug}»: ветвление запрещено; "
                f"следующей уже является «{computed_next[previous_slug]}»"
            )
        else:
            computed_next[previous_slug] = current_slug
            if quiz.get("published") and not target.get("published"):
                errors.append(
                    f"{current_label}.previous_quiz: проблемный slug «{previous_slug}»: "
                    "опубликованная викторина не может ссылаться на неопубликованную"
                )

    for start_slug, (_, start_type) in quiz_sources.items():
        seen: set[str] = set()
        slug = start_slug
        while slug in quiz_by_slug and quiz_sources.get(slug, ("", ""))[1] == start_type:
            if slug in seen:
                label = quiz_sources[start_slug][0]
                errors.append(f"{label}.previous_quiz: проблемный slug «{slug}»: обнаружен цикл")
                break
            seen.add(slug)
            previous = quiz_by_slug[slug].get("previous_quiz")
            if not isinstance(previous, str) or not previous:
                break
            slug = previous

    for previous_slug, next_slug in computed_next.items():
        quiz_by_slug[previous_slug]["next_quiz"] = next_slug
    if errors:
        raise ContentError("\n".join(errors))
    return [normalize_quiz(quiz) for quiz in quizzes]


def normalize_quiz(source: dict) -> dict:
    quiz = copy.deepcopy(source)
    slug = quiz["slug"]
    if quiz.get("type") == VOCABULARY_TYPE:
        quiz.pop("questions", None)
        quiz.pop("table", None)
        if quiz.get("parts"):
            quiz.pop("vocabulary", None)
        version_data = json.dumps(quiz, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        quiz["content_version"] = hashlib.sha256(version_data).hexdigest()
        return quiz
    for q_index, question in enumerate(quiz["questions"], 1):
        question.pop("image_alt", None)
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
            "question_count": quiz.get("word_count", len(quiz.get("questions", quiz.get("vocabulary", [])))),
            **({"type": VOCABULARY_TYPE} if quiz.get("type") == VOCABULARY_TYPE else {}),
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
    shutil.copy2(ROOT / "img" / "site-preview.webp", output / "img" / "site-preview.webp")
    shutil.copytree(ROOT / "data" / "tags", output / "data" / "tags")
    quiz_output = output / "data" / "quizzes"
    quiz_output.mkdir(parents=True)
    for quiz in quizzes:
        for question in quiz.get("questions", []):
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
    try:
        generate_share_pages(ROOT, output / "v")
    except SharePageError as error:
        raise ContentError(str(error)) from error
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
