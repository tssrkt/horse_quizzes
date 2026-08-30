#!/usr/bin/env python3
"""Generate the canonical bilingual XML sitemap."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"

ET.register_namespace("", SITEMAP_NS)
ET.register_namespace("xhtml", XHTML_NS)


def _add_url(urlset: ET.Element, location: str, alternates: dict[str, str] | None = None) -> None:
    entry = ET.SubElement(urlset, f"{{{SITEMAP_NS}}}url")
    ET.SubElement(entry, f"{{{SITEMAP_NS}}}loc").text = location
    for language, href in (alternates or {}).items():
        ET.SubElement(
            entry,
            f"{{{XHTML_NS}}}link",
            {"rel": "alternate", "hreflang": language, "href": href},
        )


def _bilingual(public_url: str, russian_path: str, english_path: str) -> dict[str, str]:
    russian_url = f"{public_url}{russian_path}"
    return {
        "ru": russian_url,
        "en": f"{public_url}{english_path}",
        "x-default": russian_url,
    }


def generate(output: Path, quizzes: list[dict], public_url: str) -> int:
    """Write sitemap.xml for published catalog entries and return its URL count."""
    urlset = ET.Element(f"{{{SITEMAP_NS}}}urlset")

    static_pairs = (
        ("", "en/"),
        ("quizzes.html", "en/quizzes.html"),
        ("contacts.html", "en/contacts.html"),
    )
    for russian_path, english_path in static_pairs:
        alternates = _bilingual(public_url, russian_path, english_path)
        _add_url(urlset, alternates["ru"], alternates)

    english_by_source = {
        quiz["source_quiz"]: quiz
        for quiz in quizzes
        if quiz.get("type") == "english" and quiz.get("published") is True
    }
    russian_quizzes = sorted(
        (
            quiz
            for quiz in quizzes
            if quiz.get("type") != "english" and quiz.get("published") is True
        ),
        key=lambda quiz: quiz["slug"],
    )
    for quiz in russian_quizzes:
        path = f"v/{quiz['slug']}/"
        alternates = None
        if quiz.get("type") != "vocabulary" and quiz["slug"] in english_by_source:
            alternates = _bilingual(public_url, path, f"en/v/{quiz['slug']}/")
        _add_url(urlset, f"{public_url}{path}", alternates)

    for quiz in sorted(english_by_source.values(), key=lambda quiz: quiz["source_quiz"]):
        source_slug = quiz["source_quiz"]
        alternates = _bilingual(public_url, f"v/{source_slug}/", f"en/v/{source_slug}/")
        _add_url(urlset, alternates["en"], alternates)

    for russian_path, english_path in static_pairs:
        alternates = _bilingual(public_url, russian_path, english_path)
        _add_url(urlset, alternates["en"], alternates)

    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ")
    xml = ET.tostring(urlset, encoding="utf-8")
    (output / "sitemap.xml").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml + b"\n"
    )
    return len(urlset)
