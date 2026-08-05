#!/usr/bin/env python3
"""Remove CMS-deleted tag slugs from both source quiz collections."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


QUIZ_DIRECTORIES = ("data/quizzes", "data/vocabulary-quizzes")


def deleted_tag_slugs(root: Path, previous_ref: str) -> set[str]:
    if not previous_ref or set(previous_ref) == {"0"}:
        return set()
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=D", previous_ref, "HEAD", "--", "data/tags/*.json"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    return {Path(line.strip()).stem for line in result.stdout.splitlines() if line.strip()}


def cleanup(root: Path, removed_slugs: set[str]) -> list[Path]:
    if not removed_slugs:
        return []
    updates: list[tuple[Path, bytes, dict]] = []
    for directory in QUIZ_DIRECTORIES:
        for path in sorted((root / directory).glob("*.json")):
            original = path.read_bytes()
            data = json.loads(original.decode("utf-8"))
            tags = data.get("tags")
            if not isinstance(tags, list):
                continue
            filtered = [tag for tag in tags if tag not in removed_slugs]
            if filtered != tags:
                data["tags"] = filtered
                updates.append((path, original, data))

    temporary: list[tuple[Path, Path]] = []
    replaced: list[tuple[Path, bytes]] = []
    try:
        for path, _, data in updates:
            handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temp_path = Path(name)
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            temporary.append((temp_path, path))
        for (temp_path, path), (_, original, _) in zip(temporary, updates):
            temp_path.replace(path)
            replaced.append((path, original))
    except Exception:
        for path, original in reversed(replaced):
            handle, name = tempfile.mkstemp(prefix=f".{path.name}.rollback.", suffix=".tmp", dir=path.parent)
            rollback = Path(name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(original)
            rollback.replace(path)
        raise
    finally:
        for temp_path, _ in temporary:
            temp_path.unlink(missing_ok=True)
    return [path for path, _, _ in updates]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--previous-ref", default="")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        slugs = deleted_tag_slugs(root, args.previous_ref)
        changed = cleanup(root, slugs)
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Не удалось согласовать удаление тегов: {error}")
        return 1
    if slugs:
        print(f"Удалённые теги: {', '.join(sorted(slugs))}; обновлено викторин: {len(changed)}.")
    else:
        print("Удалённых тегов нет.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
