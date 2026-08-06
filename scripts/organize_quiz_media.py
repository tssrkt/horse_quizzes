#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.normalize_quiz_ids import IdNormalizationError, normalize_quiz_ids


IMAGE_EXTENSIONS = {
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}

MANAGED_ROOTS = (
    PurePosixPath("img/covers"),
    PurePosixPath("img/quiz"),
)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"Некорректный slug: {value!r}")
    return slug


def normalize_repo_path(value: Any) -> PurePosixPath | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")

    if not normalized:
        return None

    path = PurePosixPath(normalized)
    if ".." in path.parts:
        raise ValueError(f"Недопустимый путь с '..': {value}")

    for root in MANAGED_ROOTS:
        if path == root or root in path.parents:
            return path

    return None


def repo_path(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


def load_quizzes(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    quiz_roots = (root / "data" / "quizzes", root / "data" / "vocabulary-quizzes", root / "data" / "english-quizzes")
    if not quiz_roots[0].is_dir():
        raise FileNotFoundError(f"Не найдена папка: {quiz_roots[0]}")

    loaded: list[tuple[Path, dict[str, Any]]] = []
    errors: list[str] = []

    paths = [path for quiz_root in quiz_roots if quiz_root.is_dir() for path in quiz_root.rglob("*.json")]
    for json_path in sorted(paths):
        try:
            value = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise TypeError("корень JSON должен быть объектом")
            loaded.append((json_path, value))
        except Exception as error:
            errors.append(f"{json_path.relative_to(root).as_posix()}: {error}")

    if errors:
        raise RuntimeError(
            "Организация изображений отменена из-за ошибок JSON:\n"
            + "\n".join(f"- {item}" for item in errors)
        )

    if not loaded:
        raise RuntimeError("Не найдено ни одной викторины.")

    return loaded


def collect_image_references(value: Any) -> Counter[PurePosixPath]:
    counts: Counter[PurePosixPath] = Counter()
    if isinstance(value, dict):
        for child in value.values():
            counts.update(collect_image_references(child))
    elif isinstance(value, list):
        for child in value:
            counts.update(collect_image_references(child))
    elif isinstance(value, str):
        candidate = value.strip().replace("\\", "/").lstrip("/")
        if not any(candidate == root.as_posix() or candidate.startswith(root.as_posix() + "/") for root in MANAGED_ROOTS):
            return counts
        image = normalize_repo_path(value)
        if image is not None:
            counts[image] += 1
    return counts


def collect_original_reference_counts(
    quizzes: list[tuple[Path, dict[str, Any]]],
) -> Counter[PurePosixPath]:
    counts: Counter[PurePosixPath] = Counter()
    for _, quiz in quizzes:
        counts.update(collect_image_references(quiz))
    return counts


def collect_current_data_references(root: Path) -> Counter[PurePosixPath]:
    counts: Counter[PurePosixPath] = Counter()
    errors: list[str] = []
    for path in sorted((root / "data").rglob("*.json")):
        try:
            counts.update(collect_image_references(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, TypeError) as error:
            errors.append(f"{path.relative_to(root).as_posix()}: {error}")
    if errors:
        raise RuntimeError("Не удалось проверить текущие ссылки на изображения:\n" + "\n".join(errors))
    return counts


def collect_references_from_git(root: Path, ref: str) -> Counter[PurePosixPath]:
    """Read all managed image references from quiz JSON files at a Git ref."""
    if not ref or set(ref) == {"0"}:
        return Counter()
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", "data"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    counts: Counter[PurePosixPath] = Counter()
    errors: list[str] = []
    for repository_path in listing:
        if not repository_path.endswith(".json"):
            continue
        result = subprocess.run(
            ["git", "show", f"{ref}:{repository_path}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        try:
            counts.update(collect_image_references(json.loads(result.stdout)))
        except (json.JSONDecodeError, TypeError) as error:
            errors.append(f"{repository_path}: {error}")
    if errors:
        raise RuntimeError("Не удалось проверить прежние ссылки на изображения:\n" + "\n".join(errors))
    return counts


def read_source_bytes(
    root: Path,
    references: Counter[PurePosixPath],
) -> dict[PurePosixPath, bytes]:
    payloads: dict[PurePosixPath, bytes] = {}
    missing: list[str] = []

    for relative in references:
        absolute = repo_path(root, relative)
        if not absolute.is_file():
            recover_deleted_media(root, relative)
        if not absolute.is_file():
            missing.append(relative.as_posix())
            continue
        payloads[relative] = absolute.read_bytes()

    if missing:
        raise RuntimeError(
            "Организация отменена: JSON ссылается на отсутствующие изображения:\n"
            + "\n".join(f"- {item}" for item in missing)
        )

    return payloads


def recover_deleted_media(root: Path, relative: PurePosixPath) -> bool:
    """Restore an exactly matching CMS media path from repository history."""
    repository_path = relative.as_posix()
    try:
        history = subprocess.run(
            ["git", "log", "--all", "--format=%H", "--", repository_path],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for commit in history:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{repository_path}"],
                cwd=root,
                check=False,
                capture_output=True,
            )
            if blob.returncode != 0:
                continue
            destination = repo_path(root, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(blob.stdout)
            print(f"ВОССТАНОВЛЕН УДАЛЁННЫЙ МЕДИАФАЙЛ: {repository_path}")
            return True
    except (OSError, subprocess.CalledProcessError):
        pass
    return False


def remove_same_stem_variants(
    directory: Path,
    stem: str,
    keep: Path,
    dry_run: bool,
) -> None:
    if not directory.is_dir():
        return

    for candidate in directory.iterdir():
        if (
            candidate.is_file()
            and candidate.stem == stem
            and candidate.suffix.lower() in IMAGE_EXTENSIONS
            and candidate != keep
        ):
            print(
                ("БУДЕТ УДАЛЁН СТАРЫЙ ВАРИАНТ: " if dry_run else "УДАЛЁН СТАРЫЙ ВАРИАНТ: ")
                + candidate.as_posix()
            )
            if not dry_run:
                candidate.unlink()


def write_bytes_if_changed(path: Path, content: bytes, dry_run: bool) -> bool:
    if path.is_file() and path.read_bytes() == content:
        return False

    if dry_run:
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def organize_quizzes(
    root: Path,
    quizzes: list[tuple[Path, dict[str, Any]]],
    source_bytes: dict[PurePosixPath, bytes],
    dry_run: bool,
) -> set[PurePosixPath]:
    final_references: set[PurePosixPath] = set()

    for json_path, quiz in quizzes:
        slug = safe_slug(str(quiz.get("slug") or json_path.stem))
        try:
            changed = normalize_quiz_ids(
                quiz,
                json_path.relative_to(root).as_posix(),
            )
        except IdNormalizationError as error:
            raise TypeError(str(error)) from None

        cover_source = normalize_repo_path(quiz.get("cover"))
        if cover_source is not None:
            # Pages CMS already stores the uploaded cover in img/covers and writes
            # that exact repository path to JSON. Preserve it byte-for-byte: using
            # the quiz slug here would desynchronise the field from the upload.
            final_references.add(cover_source)

        questions = quiz.get("questions")
        if quiz.get("type") == "vocabulary" and questions is None:
            questions = []
        if not isinstance(questions, list):
            raise TypeError(
                f"{json_path.relative_to(root).as_posix()}: questions должен быть массивом"
            )

        if quiz.get("type") == "english":
            for index, question in enumerate(questions, start=1):
                if not isinstance(question, dict):
                    raise TypeError(f"{json_path.relative_to(root).as_posix()}: вопрос {index} должен быть объектом")
                image_source = normalize_repo_path(question.get("image"))
                if image_source is not None:
                    if image_source not in source_bytes:
                        raise FileNotFoundError(f"{json_path.relative_to(root).as_posix()}: отсутствует изображение {image_source}")
                    final_references.add(image_source)
            continue

        quiz_image_dir = root / "img" / "quiz" / slug

        for index, question in enumerate(questions, start=1):
            if not isinstance(question, dict):
                raise TypeError(
                    f"{json_path.relative_to(root).as_posix()}: "
                    f"вопрос {index} должен быть объектом"
                )

            image_source = normalize_repo_path(question.get("image"))
            if image_source is None:
                continue

            suffix = image_source.suffix.lower()
            stable_stem = f"{index:02d}"
            image_target = (
                PurePosixPath("img/quiz") / slug / f"{stable_stem}{suffix}"
            )
            image_target_abs = repo_path(root, image_target)

            remove_same_stem_variants(
                quiz_image_dir,
                stable_stem,
                image_target_abs,
                dry_run,
            )

            if write_bytes_if_changed(
                image_target_abs,
                source_bytes[image_source],
                dry_run,
            ):
                print(
                    ("БУДЕТ ЗАПИСАНО ИЗОБРАЖЕНИЕ: " if dry_run else "ЗАПИСАНО ИЗОБРАЖЕНИЕ: ")
                    + image_target.as_posix()
                )

            if question.get("image") != image_target.as_posix():
                question["image"] = image_target.as_posix()
                changed = True

            final_references.add(image_target)

        if changed:
            print(
                ("БУДЕТ ОБНОВЛЁН JSON: " if dry_run else "ОБНОВЛЁН JSON: ")
                + json_path.relative_to(root).as_posix()
            )
            if not dry_run:
                json_path.write_text(
                    json.dumps(quiz, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )

    return final_references


def collect_managed_images(root: Path) -> list[Path]:
    files: list[Path] = []

    for relative_root in MANAGED_ROOTS:
        absolute_root = repo_path(root, relative_root)
        if not absolute_root.exists():
            continue

        for candidate in absolute_root.rglob("*"):
            if (
                candidate.is_file()
                and not candidate.is_symlink()
                and candidate.suffix.lower() in IMAGE_EXTENSIONS
            ):
                files.append(candidate)

    return sorted(files)


def cleanup_unreferenced(
    root: Path,
    final_references: set[PurePosixPath],
    dry_run: bool,
    candidates: set[PurePosixPath] | None = None,
) -> None:
    candidates = candidates or set()
    for relative in sorted(candidates):
        if not any(relative == managed_root or managed_root in relative.parents for managed_root in MANAGED_ROOTS):
            continue
        if relative in final_references:
            continue
        candidate = repo_path(root, relative)
        if not candidate.is_file() or candidate.is_symlink() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        print(
            ("БУДЕТ УДАЛЁН НЕИСПОЛЬЗУЕМЫЙ ФАЙЛ: " if dry_run else "УДАЛЁН НЕИСПОЛЬЗУЕМЫЙ ФАЙЛ: ")
            + relative.as_posix()
        )
        if not dry_run:
            candidate.unlink()

    for relative_root in MANAGED_ROOTS:
        absolute_root = repo_path(root, relative_root)
        if not absolute_root.is_dir():
            continue

        directories = sorted(
            (path for path in absolute_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            if any(directory.iterdir()):
                continue
            print(
                ("БУДЕТ УДАЛЕНА ПУСТАЯ ПАПКА: " if dry_run else "УДАЛЕНА ПУСТАЯ ПАПКА: ")
                + directory.relative_to(root).as_posix()
            )
            if not dry_run:
                directory.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Организует медиа викторин по папкам slug, "
            "задаёт стабильные имена и удаляет неиспользуемые копии."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать изменения без записи и удаления.",
    )
    parser.add_argument(
        "--previous-ref",
        default="",
        help="Git ref до CMS-сохранения; используются только исчезнувшие с него ссылки.",
    )
    parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Корень репозитория; по умолчанию текущая папка.",
    )
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    if not (root / ".git").exists():
        raise RuntimeError(f"Это не корень Git-репозитория: {root}")

    quizzes = load_quizzes(root)
    original_references = collect_original_reference_counts(quizzes)
    previous_references = collect_references_from_git(root, args.previous_ref)
    source_bytes = read_source_bytes(root, original_references)

    final_references = organize_quizzes(
        root,
        quizzes,
        source_bytes,
        args.dry_run,
    )
    current_references = collect_current_data_references(root)
    cleanup_candidates = set(previous_references) - set(current_references)
    cleanup_candidates.update(set(original_references) - final_references)
    protected_references = final_references | set(current_references)
    cleanup_unreferenced(root, protected_references, args.dry_run, cleanup_candidates)

    print()
    print(f"Обработано викторин: {len(quizzes)}")
    print(f"Итоговых используемых изображений: {len(final_references)}")
    if args.dry_run:
        print("Это был предварительный просмотр; файлы не изменены.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        raise SystemExit(1)
