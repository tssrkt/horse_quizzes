#!/usr/bin/env python3
"""Create or incrementally synchronize an English quiz from a Russian source."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSLATABLE_QUIZ_FIELDS = ("title", "short_description", "intro", "questionImagesAlt")
SYNCHRONIZED_QUIZ_FIELDS = ("difficulty", "cover", "publication_date")
TRANSLATABLE_QUESTION_FIELDS = ("question", "explanation")
QUESTION_SERVICE_FIELDS = ("image", "image_source", "image_author", "image_source_url")
PROMPT = """Translate the supplied Russian horse-quiz text into natural English.
Use established English equestrian terminology and, where relevant, correct veterinary and genetic terminology.
Preserve meaning exactly. Do not change correct answers, identifiers, data structure, item order, images, or service fields.
Return one translation for every key and no additional keys."""


class SyncError(RuntimeError):
    pass


def source_snapshot(source: dict) -> dict:
    return {
        **{field: source.get(field, "") for field in TRANSLATABLE_QUIZ_FIELDS},
        **{field: source.get(field, "") for field in SYNCHRONIZED_QUIZ_FIELDS},
        "tags": copy.deepcopy(source.get("tags", [])),
        "questions": copy.deepcopy(source.get("questions", [])),
    }


def snapshot_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def english_slug(source_slug: str) -> str:
    return f"{source_slug}-en"


def openai_translate(items: dict[str, str], api_key: str, model: str) -> dict[str, str]:
    if not items:
        return {}
    schema = {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["key", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }
    body = {
        "model": model,
        "reasoning": {"effort": "low"},
        "store": False,
        "instructions": PROMPT,
        "input": json.dumps([{"key": key, "text": text} for key, text in items.items()], ensure_ascii=False),
        "text": {"format": {"type": "json_schema", "name": "quiz_translation", "strict": True, "schema": schema}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise SyncError(f"OpenAI API returned HTTP {error.code}: {detail}") from None
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"OpenAI API request failed: {error}") from None
    text = next((part.get("text") for output in result.get("output", []) for part in output.get("content", []) if part.get("type") == "output_text"), None)
    if not isinstance(text, str):
        raise SyncError("OpenAI API response does not contain output_text")
    try:
        rows = json.loads(text)["translations"]
        translated = {row["key"]: row["text"].strip() for row in rows}
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise SyncError(f"Invalid structured translation response: {error}") from None
    missing = set(items) - set(translated)
    extra = set(translated) - set(items)
    if missing or extra or any(not value for value in translated.values()):
        raise SyncError(f"Translation keys mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    return translated


def plan_sync(source: dict, existing: dict | None) -> tuple[dict, dict[str, str], list[str], str]:
    old_snapshot = existing.get("_translation_source", {}) if existing else {}
    target = copy.deepcopy(existing) if existing else {}
    texts: dict[str, str] = {}
    changes: list[str] = []
    mode = "updated" if existing else "created"

    synchronized_fields = {field: source.get(field, "") for field in SYNCHRONIZED_QUIZ_FIELDS}
    if existing:
        for field, value in synchronized_fields.items():
            if target.get(field) != value:
                changes.append(f"quiz service field: {field}")
    target.update({
        "type": "english", "slug": target.get("slug") or english_slug(source["slug"]),
        "source_quiz": source["slug"], **synchronized_fields,
        "tags": ["english", *[tag for tag in source.get("tags", []) if tag != "english"]],
    })
    if not existing:
        target["published"] = False
        target["translation_status"] = "current"
    elif old_snapshot.get("tags") != source.get("tags", []):
        changes.append("quiz tags")

    for field in TRANSLATABLE_QUIZ_FIELDS:
        value = source.get(field, "")
        if not existing or old_snapshot.get(field) != value:
            if value:
                texts[f"quiz.{field}"] = value
            else:
                target.pop(field, None)
            changes.append(f"quiz field: {field}")

    old_questions = {item.get("id"): item for item in old_snapshot.get("questions", []) if isinstance(item, dict)}
    english_questions = {item.get("id"): item for item in target.get("questions", []) if isinstance(item, dict)}
    source_ids = {item.get("id") for item in source["questions"]}
    for removed_id in english_questions.keys() - source_ids:
        changes.append(f"removed question: {removed_id}")
    rebuilt = []
    for position, question in enumerate(source["questions"], 1):
        qid = question["id"]
        old_question = old_questions.get(qid, {})
        english_question = copy.deepcopy(english_questions.get(qid, {"id": qid}))
        if qid not in english_questions:
            changes.append(f"added question #{position}: {qid}")
        for field in TRANSLATABLE_QUESTION_FIELDS:
            if qid not in english_questions or old_question.get(field) != question.get(field):
                texts[f"question.{qid}.{field}"] = question[field]
                changes.append(f"question #{position} {field}: {qid}")
        for field in QUESTION_SERVICE_FIELDS:
            if field in question:
                if old_question.get(field) != question.get(field):
                    changes.append(f"question #{position} {field}: {qid}")
                english_question[field] = copy.deepcopy(question[field])
            else:
                english_question.pop(field, None)
        old_answers = {item.get("id"): item for item in old_question.get("answers", []) if isinstance(item, dict)}
        english_answers = {item.get("id"): item for item in english_question.get("answers", []) if isinstance(item, dict)}
        answer_ids = {item.get("id") for item in question["answers"]}
        for removed_id in english_answers.keys() - answer_ids:
            changes.append(f"removed answer {removed_id} from {qid}")
        rebuilt_answers = []
        for answer in question["answers"]:
            aid = answer["id"]
            english_answer = copy.deepcopy(english_answers.get(aid, {"id": aid}))
            if aid not in english_answers or old_answers.get(aid, {}).get("text") != answer.get("text"):
                texts[f"answer.{qid}.{aid}.text"] = answer["text"]
                changes.append(f"answer {aid} in {qid}")
            rebuilt_answers.append(english_answer)
        english_question["answers"] = rebuilt_answers
        if english_question.get("correct_answer_id") != question["correct_answer_id"]:
            changes.append(f"question #{position} correct answer: {qid}")
        english_question["correct_answer_id"] = question["correct_answer_id"]
        rebuilt.append(english_question)
    if existing and [q.get("id") for q in target.get("questions", [])] != [q["id"] for q in source["questions"]]:
        changes.append("question order")
    target["questions"] = rebuilt
    target["_translation_source"] = source_snapshot(source)
    target["source_content_hash"] = snapshot_hash(target["_translation_source"])
    target["translation_status"] = "current"
    return target, texts, list(dict.fromkeys(changes)), mode


def apply_translations(target: dict, translations: dict[str, str]) -> None:
    questions = {q["id"]: q for q in target["questions"]}
    for key, value in translations.items():
        parts = key.split(".")
        if parts[0] == "quiz":
            target[parts[1]] = value
        elif parts[0] == "question":
            questions[parts[1]][parts[2]] = value
        elif parts[0] == "answer":
            answer = next(item for item in questions[parts[1]]["answers"] if item["id"] == parts[2])
            answer["text"] = value


def sync(source_path: Path, output_dir: Path, translator) -> tuple[Path, str, list[str]]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("type", "quiz") != "quiz" or source_path.parent.name != "quizzes":
        raise SyncError("Only a regular Russian quiz can be translated")
    output_dir.mkdir(parents=True, exist_ok=True)
    matches = []
    for path in output_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source_quiz") == source["slug"]:
            matches.append((path, data))
    if len(matches) > 1:
        raise SyncError(f"Duplicate English versions for {source['slug']}")
    output_path, existing = matches[0] if matches else (output_dir / f"{english_slug(source['slug'])}.json", None)
    target, texts, changes, mode = plan_sync(source, existing)
    link_changed = source.get("english_quiz") != target["slug"]
    if link_changed:
        changes.append("Russian source link: english_quiz")
    if existing and not changes:
        return output_path, "unchanged", []
    apply_translations(target, translator(texts))
    source["english_quiz"] = target["slug"]
    temporary = output_path.with_suffix(".json.tmp")
    source_temporary = source_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    source_temporary.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(output_path)
    source_temporary.replace(source_path)
    return output_path, mode, changes


def summary(path: Path, mode: str, changes: list[str], warnings: list[str] | None = None) -> str:
    action = {"created": "Created a new English draft", "updated": "Updated the existing English version", "unchanged": "English version is already current"}[mode]
    lines = [f"## English quiz translation", "", f"- Result: **{action}**", f"- JSON: `{path.as_posix()}`", "", "### Changes"]
    lines.extend([f"- {item}" for item in changes] or ["- No changes detected"])
    if warnings:
        lines.extend(["", "### Warnings", *[f"- {item}" for item in warnings]])
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
            payload = json.loads(args.payload)
            relative = payload.get("context", {}).get("path")
            if not relative:
                raise SyncError("Pages CMS payload does not contain context.path")
            source_path = root / relative
        elif args.source:
            source_path = args.source if args.source.is_absolute() else root / args.source
        else:
            raise SyncError("--source or --payload is required")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SyncError("OPENAI_API_KEY is not configured")
        model = os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-5.6-terra")
        path, mode, changes = sync(source_path.resolve(), root / "data/english-quizzes", lambda items: openai_translate(items, api_key, model))
        text = summary(path.relative_to(root), mode, changes)
        if args.summary:
            args.summary.write_text(text, encoding="utf-8")
        print(text)
        return 0
    except (SyncError, OSError, json.JSONDecodeError) as error:
        text = f"## English quiz translation\n\n- Result: **failed**\n- Error: {error}\n"
        if args.summary:
            args.summary.write_text(text, encoding="utf-8")
        print(text, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
