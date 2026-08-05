#!/usr/bin/env python3
"""Mark English translations outdated when their Russian source snapshot changed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.sync_english_quiz import ROOT, snapshot_hash, source_snapshot


def mark_stale(root: Path = ROOT) -> list[Path]:
    sources = {}
    for path in (root / "data/quizzes").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        sources[data.get("slug")] = data
    changed = []
    for path in sorted((root / "data/english-quizzes").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        source = sources.get(data.get("source_quiz"))
        if not source:
            continue
        expected = snapshot_hash(source_snapshot(source))
        status = "current" if data.get("source_content_hash") == expected else "outdated"
        if data.get("translation_status") == status:
            continue
        data["translation_status"] = status
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(path)
        changed.append(path)
    return changed


if __name__ == "__main__":
    updated = mark_stale()
    print(f"Статус английских переводов обновлён: {len(updated)}.")
