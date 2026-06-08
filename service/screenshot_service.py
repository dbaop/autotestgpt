"""
Screenshot persistence — save base64 data URLs to disk and return relative paths.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)


def ensure_screenshot_dir() -> str:
    """Create the screenshot directory if it doesn't exist. Return absolute path."""
    abs_dir = str(Path(Config.SCREENSHOT_DIR).resolve())
    os.makedirs(abs_dir, exist_ok=True)
    return abs_dir


def save_screenshot_from_data_url(data_url: str, prefix: str = "exec") -> Optional[str]:
    """Decode a base64 PNG data URL and write it to disk.

    Returns the relative path (e.g. "screenshots/exec_20260101_120000_123456.png")
    so it can be stored in ExecutionRecord.screenshot_paths.
    """
    try:
        m = re.match(r"data:image/\w+;base64,(.+)", data_url)
        if not m:
            logger.warning("Malformed data URL (no base64 body)")
            return None

        raw = base64.b64decode(m.group(1))
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{stamp}.png"

        abs_dir = ensure_screenshot_dir()
        full_path = os.path.join(abs_dir, filename)
        with open(full_path, "wb") as fh:
            fh.write(raw)

        rel = f"screenshots/{filename}"
        logger.info("Screenshot saved: %s (%d bytes)", rel, len(raw))
        return rel
    except Exception as exc:
        logger.warning("Failed to save screenshot: %s", exc)
        return None


def resolve_screenshot_path(relative_path: str) -> Optional[str]:
    """Resolve a relative screenshot path to an absolute filesystem path."""
    candidate = Path(Config.SCREENSHOT_DIR) / Path(relative_path).name
    resolved = candidate.resolve()
    if resolved.exists() and resolved.is_file():
        return str(resolved)
    return None


def build_screenshot_url(relative_path: str) -> str:
    """Build a frontend-accessible URL for a screenshot."""
    return f"/{relative_path}"
