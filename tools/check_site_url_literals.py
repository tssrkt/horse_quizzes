#!/usr/bin/env python3
"""Reject duplicated repository/Page URL literals outside explicit generated fixtures."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "_site", "v", "tests", "img", "data", ".pytest_cache"}
PATTERNS = (
    re.compile(r"https://tssrkt\.github\.io/(?:quiz|horse_quizzes)/?"),
    re.compile(r"tssrkt/quiz"),
    re.compile(r'''["']/(?:quiz|horse_quizzes)/'''),
)
# site.json is the source of truth; this checker necessarily contains the
# forbidden spellings as regexes used to detect them.
ALLOW = {Path("site.json"), Path("tools/check_site_url_literals.py")}


def violations(root: Path = ROOT) -> list[str]:
    found = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts) or relative in ALLOW:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                found.append(f"{relative.as_posix()}:{number}: {line.strip()}")
    return found


def main() -> int:
    found = violations()
    if found:
        print("Duplicated site/repository URL literals found outside site.json:", file=sys.stderr)
        print("\n".join(found), file=sys.stderr)
        return 1
    print("Site URL literal check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
