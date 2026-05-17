"""
Narrator — generates per-scene voiceover audio using edge-tts.

edge-tts uses Microsoft's Azure Cognitive Services TTS via an unofficial
but stable public endpoint — completely free, no API key required.

Default voice: en-US-GuyNeural (US male, warm and engaging)
Other good options:
  - en-US-ChristopherNeural  (US male, authoritative)
  - en-US-EricNeural         (US male, casual)
  - en-GB-RyanNeural         (UK male, polished)
  - en-AU-WilliamNeural      (Australian male)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import Config


# ── Core TTS call ─────────────────────────────────────────────────────────────

async def _synthesize(text: str, output_path: Path, voice: str) -> None:
    """Synthesize text to speech and save as MP3."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+0%", pitch="+0Hz")
    await communicate.save(str(output_path))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def synthesize_scene(text: str, output_path: Path, voice: str | None = None) -> Path:
    """
    Generate voiceover for a single scene.

    Args:
        text: Narration text to speak
        output_path: Where to save the .mp3 file
        voice: edge-tts voice name (defaults to Config.DEFAULT_VOICE)

    Returns:
        Path to the generated audio file
    """
    voice = voice or Config.DEFAULT_VOICE
    output_path.parent.mkdir(parents=True, exist_ok=True)

    asyncio.run(_synthesize(text, output_path, voice))
    return output_path


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

            audio_path = Config.audio_dir() / f"{slug}_scene_{scene_num:02d}.mp3"

            if progress_callback:
                progress_callback(
                    f"Generating narration: Scene {scene_num} — {scene['title'][:40]}...",
                    i + 1,
                    len(scenes),
                )

            synthesize_scene(narration, audio_path, self.voice)
            results.append({"scene_number": scene_num, "audio_path": audio_path})

        return results

    @staticmethod
    def list_voices() -> list[dict]:
        """Return available edge-tts voices (async wrapper)."""
        async def _get():
            return await edge_tts.list_voices()
        voices = asyncio.run(_get())
        # Filter to English only for display
        return [v for v in voices if v["Locale"].startswith("en-")]
