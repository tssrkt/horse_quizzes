#!/usr/bin/env python3
"""Validate and atomically import a translated ChatGPT JSON package."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.sync_english_quiz import FORMAT_VERSION, ROOT, SyncError, make_package, snapshot_hash, source_snapshot

TOP_LEVEL_KEYS = {"format_version", "translation_instructions", "status", "source_quiz", "target_quiz", "source_revision", "mode", "fields", "questions"}


def _assert_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SyncError(f"{label}: translated text must be a non-empty string")


def validate_structure(package: dict, expected: dict) -> list[str]:
    if set(package) != TOP_LEVEL_KEYS:
        raise SyncError("Translation package top-level keys or structure were changed")
    if package.get("format_version") != FORMAT_VERSION:
        raise SyncError(f"Unsupported format_version: {package.get('format_version')}")
    if package.get("status") == "imported":
        raise SyncError("This translation package has already been imported")
    if package.get("status") not in {"pending", "translated"}:
        raise SyncError("Package status must be pending or translated")
    if not isinstance(package.get("translation_instructions"), str):
        raise SyncError("translation_instructions must remain a string")
    if not isinstance(package.get("fields"), dict) or set(package["fields"]) != set(expected["fields"]):
        raise SyncError("Quiz translation fields were added, removed, or renamed")
    imported = []
    for field, value in package["fields"].items():
        _assert_text(value, f"fields.{field}")
        imported.append(field)
    questions = package.get("questions")
    expected_questions = expected["questions"]
    if not isinstance(questions, list) or [q.get("id") for q in questions if isinstance(q, dict)] != [q["id"] for q in expected_questions]:
        raise SyncError("Question IDs, order, or number do not match the prepared package")
    if len({q["id"] for q in questions}) != len(questions):
        raise SyncError("Duplicate question ID in translation package")
    for question, expected_question in zip(questions, expected_questions):
        if set(question) != {"id", "fields", "answers"}:
            raise SyncError(f"Question {question.get('id')}: structure was changed")
        if not isinstance(question["fields"], dict) or set(question["fields"]) != set(expected_question["fields"]):
            raise SyncError(f"Question {question['id']}: fields were added, removed, or renamed")
        for field, value in question["fields"].items():
            _assert_text(value, f"questions.{question['id']}.{field}")
            imported.append(f"{question['id']}.{field}")
        answers = question.get("answers")
        expected_answers = expected_question["answers"]
        if not isinstance(answers, list) or [a.get("id") for a in answers if isinstance(a, dict)] != [a["id"] for a in expected_answers]:
            raise SyncError(f"Question {question['id']}: answer IDs, order, or number changed")
        if len({a["id"] for a in answers}) != len(answers):
            raise SyncError(f"Question {question['id']}: duplicate answer ID")
        for answer in answers:
            if set(answer) != {"id", "text"}:
                raise SyncError(f"Answer {answer.get('id')} in {question['id']}: structure was changed")
            _assert_text(answer["text"], f"questions.{question['id']}.answers.{answer['id']}")
            imported.append(f"{question['id']}.{answer['id']}.text")
    return imported


def apply_package(target: dict, package: dict) -> None:
    for field, value in package["fields"].items():
        target[field] = value.strip()
    questions = {question["id"]: question for question in target["questions"]}
    for translated_question in package["questions"]:
        question = questions[translated_question["id"]]
        for field, value in translated_question["fields"].items():
            question[field] = value.strip()
        answers = {answer["id"]: answer for answer in question["answers"]}
        for translated_answer in translated_question["answers"]:
            answers[translated_answer["id"]]["text"] = translated_answer["text"].strip()


def _serialized(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def import_package(package_path: Path, root: Path = ROOT) -> tuple[Path, list[str]]:
    original_package = package_path.read_bytes()
    package = json.loads(original_package.decode("utf-8"))
    source_path = root / "data/quizzes" / f"{package.get('source_quiz')}.json"
    target_path = root / "data/english-quizzes" / f"{package.get('target_quiz')}.json"
    if not source_path.is_file():
        raise SyncError(f"Russian source does not exist: {package.get('source_quiz')}")
    if not target_path.is_file():
        raise SyncError(f"English target does not exist: {package.get('target_quiz')}")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    original_target = target_path.read_bytes()
    target = json.loads(original_target.decode("utf-8"))
    if source.get("slug") != package.get("source_quiz") or target.get("slug") != package.get("target_quiz"):
        raise SyncError("Package belongs to another quiz")
    if target.get("source_quiz") != source["slug"] or source.get("english_quiz") != target["slug"]:
        raise SyncError("Russian/English quiz links do not match the package")
    revision = snapshot_hash(source_snapshot(source))
    if package.get("source_revision") != revision:
        raise SyncError("Russian source changed after this package was prepared")
    pending = target.get("_pending_translation")
    if not isinstance(pending, dict) or pending.get("source_revision") != revision or pending.get("package") != package_path.name:
        raise SyncError("Target quiz does not expect this package or it was already imported")
    old_snapshot = target.get("_translation_source", {})
    expected = make_package(source, target, old_snapshot, package.get("mode", "updated"))
    for field in ("source_quiz", "target_quiz", "source_revision", "mode"):
        if package.get(field) != expected.get(field):
            raise SyncError(f"Package {field} does not match the prepared translation")
    imported = validate_structure(package, expected)

    updated_target = copy.deepcopy(target)
    apply_package(updated_target, package)
    updated_target["_translation_source"] = source_snapshot(source)
    updated_target["source_content_hash"] = revision
    updated_target["translation_status"] = "current"
    updated_target.pop("_pending_translation", None)
    updated_package = copy.deepcopy(package)
    updated_package["status"] = "imported"

    target_temp = target_path.with_suffix(".json.tmp")
    package_temp = package_path.with_suffix(".json.tmp")
    try:
        target_temp.write_bytes(_serialized(updated_target))
        package_temp.write_bytes(_serialized(updated_package))
        target_temp.replace(target_path)
        package_temp.replace(package_path)
    except Exception:
        target_path.write_bytes(original_target)
        package_path.write_bytes(original_package)
        raise
    finally:
        target_temp.unlink(missing_ok=True)
        package_temp.unlink(missing_ok=True)
    return target_path, imported


def summary(target: Path, imported: list[str]) -> str:
    return "\n".join([
        "## Import English translation", "", "- Revision validation: **passed**",
        f"- English quiz: `{target.as_posix()}`", "", "### Imported fields",
        *([f"- {item}" for item in imported] or ["- None"]), "",
        "### Automatically synchronized elements", "- None during import (non-text changes were applied during package preparation)",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path)
    parser.add_argument("--payload")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.payload:
            relative = json.loads(args.payload).get("context", {}).get("path")
            if not relative:
                raise SyncError("Pages CMS payload does not contain context.path")
            package_path = root / relative
        elif args.package:
            package_path = args.package if args.package.is_absolute() else root / args.package
        else:
            raise SyncError("--package or --payload is required")
        target, imported = import_package(package_path.resolve(), root)
        text = summary(target.relative_to(root), imported)
        if args.summary:
            args.summary.write_text(text, encoding="utf-8")
        print(text)
        return 0
    except (SyncError, OSError, json.JSONDecodeError) as error:
        text = f"## Import English translation\n\n- Result: **rejected**\n- Error: {error}\n"
        if args.summary:
            args.summary.write_text(text, encoding="utf-8")
        print(text, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
