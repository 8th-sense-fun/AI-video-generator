"""
Narrator — generates per-scene voiceover audio using edge-tts.

edge-tts uses Microsoft's Azure Cognitive Services TTS via a public endpoint.
Requires edge-tts >= 7.2.8 which fixed the 403 WebSocket handshake issue.

Default voice: en-US-GuyNeural (US male, warm and engaging)
Other good options:
  - en-US-ChristopherNeural  (US male, authoritative)
  - en-US-EricNeural         (US male, casual)
  - en-GB-RyanNeural         (UK male, polished)
  - en-AU-WilliamNeural      (Australian male)
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import edge_tts

from src.config import Config

# Maximum attempts per scene before giving up
_MAX_ATTEMPTS = 5
_RETRY_DELAY = 3  # seconds between retries


# ── Core TTS call ─────────────────────────────────────────────────────────────

async def _synthesize(text: str, output_path: Path, voice: str) -> None:
    """Synthesize text to speech and save as MP3."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+0%", pitch="+0Hz")
    await communicate.save(str(output_path))


def synthesize_scene(text: str, output_path: Path, voice: str | None = None) -> Path:
    """
    Generate voiceover for a single scene with manual retry logic.

    Args:
        text: Narration text to speak
        output_path: Where to save the .mp3 file
        voice: edge-tts voice name (defaults to Config.DEFAULT_VOICE)

    Returns:
        Path to the generated audio file
    """
    voice = voice or Config.DEFAULT_VOICE
    output_path.parent.mkdir(parents=True, exist_ok=True)

    last_exc = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            # Create a fresh event loop per call to avoid loop reuse issues
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_synthesize(text, output_path, voice))
            finally:
                loop.close()

            if output_path.exists() and output_path.stat().st_size > 0:
                return output_path
            raise RuntimeError("Output file is empty after synthesis")

        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY * attempt)  # Back-off: 3s, 6s, 9s, 12s

    raise RuntimeError(
        f"TTS failed after {_MAX_ATTEMPTS} attempts: {last_exc}"
    ) from last_exc


# ── Main narrator class ────────────────────────────────────────────────────────

class Narrator:
    """Tier A narrator using edge-tts (free, no API key needed)."""

    def __init__(self, voice: str | None = None) -> None:
        self.voice = voice or Config.DEFAULT_VOICE

    def narrate_script(
        self,
        script: dict,
        slug: str,
        progress_callback=None,
    ) -> list[dict]:
        """
        Generate audio for all scenes in a script.

        Args:
            script: Output from ScriptWriter.write()
            slug: Unique run identifier for filenames
            progress_callback: Optional callable(message, step, total)

        Returns:
            List of dicts with scene_number and audio_path
        """
        scenes = script.get("scenes", [])
        results = []

        for i, scene in enumerate(scenes):
            scene_num = scene["scene_number"]
            narration = scene["narration"]

            # Files live inside the per-run audio folder
            audio_path = Config.audio_dir() / f"scene_{scene_num:02d}.mp3"

            if progress_callback:
                progress_callback(
                    f"Generating narration: Scene {scene_num} — {scene['title'][:40]}",
                    i + 1,
                    len(scenes),
                )

            # Skip if already generated (useful for partial re-runs)
            if audio_path.exists() and audio_path.stat().st_size > 0:
                results.append({"scene_number": scene_num, "audio_path": audio_path})
                continue

            synthesize_scene(narration, audio_path, self.voice)
            results.append({"scene_number": scene_num, "audio_path": audio_path})

        return results

    @staticmethod
    def list_voices() -> list[dict]:
        """Return available edge-tts voices (English only)."""
        async def _get():
            return await edge_tts.list_voices()
        loop = asyncio.new_event_loop()
        try:
            voices = loop.run_until_complete(_get())
        finally:
            loop.close()
        return [v for v in voices if v["Locale"].startswith("en-")]
