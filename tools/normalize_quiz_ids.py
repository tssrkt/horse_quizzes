#!/usr/bin/env python3
"""Persist missing stable question and answer IDs in source quiz JSON files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUESTION_ID_RE = re.compile(r"^question-(\d{2,})$")
ANSWER_ID_RE = re.compile(r"^answer-(\d{2,})$")


class IdNormalizationError(Exception):
    pass


def _existing_number(value: object, pattern: re.Pattern[str], label: str) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or not (match := pattern.fullmatch(value)):
        raise IdNormalizationError(f"{label}: недопустимый существующий ID «{value}»")
    return int(match.group(1))


def _assign_ids(items: list, key: str, pattern: re.Pattern[str], prefix: str, label: str) -> bool:
    seen: dict[str, int] = {}
    missing: list[tuple[int, dict]] = []
    maximum = 0
    for index, item in enumerate(items, 1):
        item_label = f"{label}[{index}]"
        if not isinstance(item, dict):
            raise IdNormalizationError(f"{item_label}: требуется объект")
        value = item.get(key)
        number = _existing_number(value, pattern, f"{item_label}.{key}")
        if number is None:
            missing.append((index, item))
            continue
        normalized = value
        if normalized in seen:
            raise IdNormalizationError(
                f"{label}: конфликтующий ID «{normalized}» у элементов {seen[normalized]} и {index}"
            )
        seen[normalized] = index
        maximum = max(maximum, number)

    changed = False
    for _, item in missing:
        maximum += 1
        item[key] = f"{prefix}-{maximum:02d}"
        changed = True
    return changed


def normalize_quiz_ids(quiz: dict, label: str = "quiz") -> bool:
    if quiz.get("type") == "vocabulary":
        return False
    questions = quiz.get("questions")
    if not isinstance(questions, list):
        raise IdNormalizationError(f"{label}.questions: требуется массив")
    changed = _assign_ids(questions, "id", QUESTION_ID_RE, "question", f"{label}.questions")
    for q_index, question in enumerate(questions, 1):
        answers = question.get("answers")
        if not isinstance(answers, list):
            raise IdNormalizationError(f"{label}.questions[{q_index}].answers: требуется массив")
        changed |= _assign_ids(
            answers,
            "id",
            ANSWER_ID_RE,
            "answer",
            f"{label}.questions[{q_index}].answers",
        )
    return changed


def normalize_file(path: Path) -> bool:
    try:
        quiz = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IdNormalizationError(f"{path}: некорректный JSON: {error}") from None
    if not isinstance(quiz, dict):
        raise IdNormalizationError(f"{path}: корневое значение должно быть объектом")
    changed = normalize_quiz_ids(quiz, str(path))
    if changed:
        path.write_text(json.dumps(quiz, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Добавить отсутствующие служебные ID в исходные JSON викторин")
    parser.add_argument("paths", nargs="*", type=Path, help="JSON-файлы; по умолчанию data/quizzes/*.json")
    args = parser.parse_args()
    paths = args.paths or sorted((ROOT / "data" / "quizzes").glob("*.json"))
    changed: list[Path] = []
    try:
        for path in paths:
            if normalize_file(path):
                changed.append(path)
    except IdNormalizationError as error:
        print(f"Ошибка нормализации ID: {error}", file=sys.stderr)
        return 1
    if changed:
        print("Добавлены отсутствующие ID: " + ", ".join(str(path) for path in changed))
    else:
        print("Нормализация ID не изменила файлы.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
