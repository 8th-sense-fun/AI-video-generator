"""
Shared utility helpers.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path


def slugify(text: str) -> str:
    """
    Convert a topic string into a safe filesystem slug.
    e.g. "US Housing Market 2026!" -> "us_housing_market_2026"
    """
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase, replace spaces and special chars with _
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:50]  # Max 50 chars


def run_slug(topic: str) -> str:
    """Generate a unique run identifier: slug + timestamp."""
    return f"{slugify(topic)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def format_duration(seconds: int) -> str:
    """Format seconds as mm:ss string."""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def print_sources_table(sources: list[dict]) -> None:
    """Print a formatted table of research sources."""
    print("\n📚 Sources Found:")
    print("─" * 80)
    for i, src in enumerate(sources, 1):
        title = src.get("title", "Untitled")[:60]
        url = src.get("url", "")[:70]
        score = src.get("score", 0)
        print(f"  {i:2}. [{score:.2f}] {title}")
        print(f"       {url}")
    print("─" * 80)
