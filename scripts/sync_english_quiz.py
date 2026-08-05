#!/usr/bin/env python3
"""Prepare English quiz structure and a translation package without calling an AI API."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT_VERSION = 1
QUIZ_TEXT_FIELDS = ("title", "short_description", "intro", "questionImagesAlt")
QUIZ_SERVICE_FIELDS = ("difficulty", "cover", "publication_date")
QUESTION_TEXT_FIELDS = ("question", "explanation")
QUESTION_SERVICE_FIELDS = ("image", "image_source", "image_author", "image_source_url")
TRANSLATION_INSTRUCTIONS = (
    "Translate only textual values into natural English using established equestrian, veterinary, and genetic terminology. "
    "Do not change JSON keys, IDs, structure, order, slugs, technical values, or add/remove elements. Do not translate tags. "
    "Preserve the meaning and correctness of every question and return valid JSON."
)


class SyncError(RuntimeError):
    pass


def source_snapshot(source: dict) -> dict:
    return {
        **{field: source.get(field, "") for field in QUIZ_TEXT_FIELDS},
        **{field: source.get(field, "") for field in QUIZ_SERVICE_FIELDS},
        "tags": copy.deepcopy(source.get("tags", [])),
        "questions": copy.deepcopy(source.get("questions", [])),
    }


def snapshot_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def english_slug(source_slug: str) -> str:
    return f"{source_slug}-en"


def translation_content(source: dict, old_snapshot: dict) -> tuple[dict, list[dict]]:
    fields = {}
    for field in QUIZ_TEXT_FIELDS:
        if old_snapshot.get(field) != source.get(field, ""):
            fields[field] = source.get(field, "")
    old_questions = {item.get("id"): item for item in old_snapshot.get("questions", []) if isinstance(item, dict)}
    questions = []
    for question in source["questions"]:
        qid = question["id"]
        old_question = old_questions.get(qid, {})
        changed_fields = {field: question[field] for field in QUESTION_TEXT_FIELDS if old_question.get(field) != question.get(field)}
        old_answers = {item.get("id"): item for item in old_question.get("answers", []) if isinstance(item, dict)}
        changed_answers = [
            {"id": answer["id"], "text": answer["text"]}
            for answer in question["answers"]
            if old_answers.get(answer["id"], {}).get("text") != answer.get("text")
        ]
        if changed_fields or changed_answers:
            entry = {"id": qid, "fields": changed_fields, "answers": changed_answers}
            questions.append(entry)
    return fields, questions


def synchronize_structure(source: dict, existing: dict | None) -> tuple[dict, list[str]]:
    target = copy.deepcopy(existing) if existing else {}
    automatic: list[str] = []
    target_slug = target.get("slug") or english_slug(source["slug"])
    for field in QUIZ_SERVICE_FIELDS:
        if existing and target.get(field) != source.get(field, ""):
            automatic.append(f"quiz service field: {field}")
        target[field] = copy.deepcopy(source.get(field, ""))
    new_tags = ["english", *[tag for tag in source.get("tags", []) if tag != "english"]]
    if existing and target.get("tags") != new_tags:
        automatic.append("quiz tags")
    target.update({"type": "english", "slug": target_slug, "source_quiz": source["slug"], "tags": new_tags})
    if not existing:
        target["published"] = False
        for field in QUIZ_TEXT_FIELDS:
            if source.get(field, ""):
                target[field] = source[field]

    existing_questions = {item.get("id"): item for item in target.get("questions", []) if isinstance(item, dict)}
    source_ids = {item["id"] for item in source["questions"]}
    for removed in existing_questions.keys() - source_ids:
        automatic.append(f"removed question: {removed}")
    rebuilt = []
    for position, question in enumerate(source["questions"], 1):
        qid = question["id"]
        current = copy.deepcopy(existing_questions.get(qid, {"id": qid}))
        added = qid not in existing_questions
        if added:
            automatic.append(f"added question #{position}: {qid}")
            for field in QUESTION_TEXT_FIELDS:
                current[field] = question[field]
        for field in QUESTION_SERVICE_FIELDS:
            current_value = current.get(field) if field in current else None
            source_value = question.get(field) if field in question else None
            if current_value != source_value and not added:
                automatic.append(f"question #{position} {field}: {qid}")
            if field in question:
                current[field] = copy.deepcopy(question[field])
            else:
                current.pop(field, None)
        existing_answers = {item.get("id"): item for item in current.get("answers", []) if isinstance(item, dict)}
        answer_ids = {item["id"] for item in question["answers"]}
        for removed in existing_answers.keys() - answer_ids:
            automatic.append(f"removed answer {removed} from {qid}")
        answers = []
        for answer in question["answers"]:
            aid = answer["id"]
            current_answer = copy.deepcopy(existing_answers.get(aid, {"id": aid, "text": answer["text"]}))
            if aid not in existing_answers:
                automatic.append(f"added answer {aid} to {qid}")
            answers.append(current_answer)
        if [item.get("id") for item in current.get("answers", [])] != [item["id"] for item in question["answers"]] and not added:
            automatic.append(f"answer order: {qid}")
        current["answers"] = answers
        if current.get("correct_answer_id") != question["correct_answer_id"] and not added:
            automatic.append(f"correct answer: {qid}")
        current["correct_answer_id"] = question["correct_answer_id"]
        rebuilt.append(current)
    if existing and [item.get("id") for item in target.get("questions", [])] != [item["id"] for item in source["questions"]]:
        automatic.append("question order")
    target["questions"] = rebuilt
    return target, list(dict.fromkeys(automatic))


def make_package(source: dict, target: dict, old_snapshot: dict, mode: str) -> dict:
    fields, questions = translation_content(source, old_snapshot)
    revision = snapshot_hash(source_snapshot(source))
    return {
        "format_version": FORMAT_VERSION,
        "translation_instructions": TRANSLATION_INSTRUCTIONS,
        "status": "pending",
        "source_quiz": source["slug"],
        "target_quiz": target["slug"],
        "source_revision": revision,
        "mode": mode,
        "fields": fields,
        "questions": questions,
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def prepare(source_path: Path, english_dir: Path, package_dir: Path) -> tuple[Path, Path, str, list[str], list[str]]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("type", "quiz") != "quiz" or source_path.parent.name != "quizzes":
        raise SyncError("Only a regular Russian quiz can be prepared")
    matches = []
    for path in english_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source_quiz") == source["slug"]:
            matches.append((path, data))
    if len(matches) > 1:
        raise SyncError(f"Duplicate English versions for {source['slug']}")
    target_path, existing = matches[0] if matches else (english_dir / f"{english_slug(source['slug'])}.json", None)
    old_snapshot = existing.get("_translation_source", {}) if existing else {}
    current_snapshot = source_snapshot(source)
    changed = not existing or snapshot_hash(old_snapshot) != snapshot_hash(current_snapshot)
    target, automatic = synchronize_structure(source, existing)
    source_link_changed = source.get("english_quiz") != target["slug"]
    if source_link_changed:
        source["english_quiz"] = target["slug"]
        automatic.append("Russian source link: english_quiz")
    mode = "created" if not existing else "updated" if changed or automatic else "unchanged"
    package_path = package_dir / f"{source['slug']}-en.json"
    package = make_package(source, target, old_snapshot, mode)
    text_items = list(package["fields"])
    text_items += [f"{q['id']}.{field}" for q in package["questions"] for field in q["fields"]]
    text_items += [f"{q['id']}.{a['id']}.text" for q in package["questions"] for a in q["answers"]]
    if mode == "unchanged":
        return target_path, package_path, mode, [], []
    if text_items:
        target["translation_status"] = "outdated"
        target["_pending_translation"] = {"source_revision": package["source_revision"], "package": package_path.name}
        target.setdefault("_translation_source", {})
        _write_json(package_path, package)
    else:
        target["translation_status"] = "current"
        target["_translation_source"] = current_snapshot
        target["source_content_hash"] = package["source_revision"]
        target.pop("_pending_translation", None)
        if package_path.exists():
            package_path.unlink()
    _write_json(target_path, target)
    if source_link_changed:
        _write_json(source_path, source)
    return target_path, package_path, mode, text_items, automatic


def summary(target: Path, package: Path, mode: str, texts: list[str], automatic: list[str]) -> str:
    lines = ["## English translation package", "", f"- Mode: **{mode}**", f"- English quiz: `{target.as_posix()}`"]
    lines.append(f"- Package: `{package.as_posix()}`" if texts else "- Package: not required")
    lines.extend(["", "### Texts requiring translation", *([f"- {item}" for item in texts] or ["- None"])])
    lines.extend(["", "### Automatically synchronized", *([f"- {item}" for item in automatic] or ["- None"])])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
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
            source_path = root / relative
        elif args.source:
            source_path = args.source if args.source.is_absolute() else root / args.source
        else:
            raise SyncError("--source or --payload is required")
        target, package, mode, texts, automatic = prepare(source_path.resolve(), root / "data/english-quizzes", root / "data/translation-packages")
        text = summary(target.relative_to(root), package.relative_to(root), mode, texts, automatic)
        if args.summary:
            args.summary.write_text(text, encoding="utf-8")
        print(text)
        return 0
    except (SyncError, OSError, json.JSONDecodeError) as error:
        text = f"## English translation package\n\n- Mode: **failed**\n- Error: {error}\n"
        if args.summary:
            args.summary.write_text(text, encoding="utf-8")
        print(text, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
