"""
Background Music Module — STUB (reserved for future use)
=========================================================
Background music is currently **not implemented**.  This module is retained as
a placeholder so the import path exists.  ``MusicProvider.get_track`` always
returns ``(None, "off")`` and is not called anywhere in the current pipeline.

To add music support in a future version, replace this stub with a real
implementation and wire it into ``src/pipeline.py`` between the narration and
assembly steps.
"""

from __future__ import annotations

from pathlib import Path


class MusicProvider:
    """Placeholder music provider — always returns no track."""

    def get_track(
        self,
        topic: str,
        duration: float,
        mood: str | None = None,
    ) -> tuple[Path | None, str]:
        """Return ``(None, 'off')`` — music is disabled in this stub."""
        return None, "off"
