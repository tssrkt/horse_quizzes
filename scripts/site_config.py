"""Load and validate the single public-site URL configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "site.json"


def load_site_config(root: Path = ROOT) -> dict[str, str]:
    path = root / "site.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: invalid site configuration: {error}") from error
    origin = os.environ.get("SITE_ORIGIN", config.get("origin"))
    base_path = os.environ.get("BASE_PATH", config.get("base_path"))
    if not isinstance(origin, str):
        raise ValueError(f"{path}: origin must be an absolute HTTP(S) origin")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError(f"{path}: origin must contain only an HTTP(S) scheme and host")
    origin = origin.rstrip("/")
    if not isinstance(base_path, str) or not base_path.startswith("/") or not base_path.endswith("/") or "//" in base_path:
        raise ValueError(f"{path}: base_path must start and end with / (use / for a root deployment)")
    return {"origin": origin, "base_path": base_path, "public_url": f"{origin}{base_path}"}
