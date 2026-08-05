#!/usr/bin/env python3
"""Persist imported vocabulary rows in JSON, then remove their source tables."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from tools import build_site


def finalize(root: Path) -> tuple[int, int]:
    quiz_dir = root / "data" / "vocabulary-quizzes"
    updates: list[tuple[Path, dict]] = []
    imported_paths: set[Path] = set()

    # Complete every import before changing JSON or deleting anything.
    for json_path in sorted(quiz_dir.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        parts = data.get("parts")
        if parts is None and data.get("table"):
            parts = [{"title": "", "table": data["table"]}]
            data["parts"] = parts
            data.pop("table", None)
        changed = False
        for part in parts or []:
            table = part.get("table") if isinstance(part, dict) else None
            if not isinstance(table, str) or not table:
                continue
            table_path = (json_path.parent / table).resolve()
            try:
                relative = table_path.relative_to(root.resolve())
            except ValueError:
                raise build_site.ContentError(f"{json_path.relative_to(root)}: путь таблицы выходит за пределы проекта: {table}") from None
            if relative.parts[:2] != ("data", "vocabulary") or table_path.suffix.lower() not in {".xlsx", ".csv"}:
                raise build_site.ContentError(f"{json_path.relative_to(root)}: недопустимый файл импорта: {table}")
            if not table_path.exists():
                if part.get("vocabulary"):
                    continue
                raise build_site.ContentError(f"{json_path.relative_to(root)}: файл импорта не найден: {table}")
            part["vocabulary"] = build_site.import_vocabulary_table(table_path)
            imported_paths.add(table_path)
            changed = True
        if changed:
            updates.append((json_path, data))

    # Atomically replace every successfully generated JSON before cleanup.
    temporary: list[tuple[Path, Path]] = []
    try:
        for json_path, data in updates:
            handle, temp_name = tempfile.mkstemp(prefix=f".{json_path.name}.", suffix=".tmp", dir=json_path.parent)
            temp_path = Path(temp_name)
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            temporary.append((temp_path, json_path))
        for temp_path, json_path in temporary:
            temp_path.replace(json_path)
    finally:
        for temp_path, _ in temporary:
            temp_path.unlink(missing_ok=True)

    for table_path in imported_paths:
        table_path.unlink()
        print(f"Удалён импортированный файл: {table_path.relative_to(root)}")
    return len(updates), len(imported_paths)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=build_site.ROOT)
    args = parser.parse_args()
    try:
        updated, removed = finalize(args.root.resolve())
    except (build_site.ContentError, OSError, json.JSONDecodeError) as error:
        print(f"Импорт словарных таблиц не завершён: {error}")
        return 1
    print(f"Импорт завершён: JSON обновлено — {updated}, таблиц удалено — {removed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
