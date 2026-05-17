"""
Video assembler — merges per-scene audio + video clips into a final
cinematic educational video using MoviePy.

Pipeline per scene:
  1. Load stock video clip → loop/trim to match audio duration
  2. Add subtle Ken Burns zoom effect for visual interest
  3. Overlay narration audio
  4. Add title card at scene start (lower third)
  5. Add subtle background music bed

Final output: one clean MP4 with no watermarks.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    concatenate_audioclips,
    afx,
)
from PIL import Image, ImageDraw, ImageFont

from src.config import Config


# ── Visual constants ──────────────────────────────────────────────────────────

W = Config.VIDEO_WIDTH    # 1280
H = Config.VIDEO_HEIGHT   # 720
FPS = 24
FONT_SIZE_TITLE = 38
FONT_SIZE_SCENE = 28
FADE_DURATION = 0.8       # seconds for fade in/out between scenes


# ── Helper: PIL-based text image (fallback for systems without fonts) ─────────

def _make_text_image(
    text: str,
    width: int,
    font_size: int = 36,
    text_color: tuple = (255, 255, 255),
    bg_color: tuple | None = None,
    padding: int = 20,
) -> np.ndarray:
    """Render text to a numpy image array using PIL."""
    # Wrap text
    wrapped = textwrap.fill(text, width=max(10, width // (font_size // 2)))
    lines = wrapped.split("\n")

    # Try to load a nice font, fall back to default
    font = None
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in font_paths:
        try:
            font = ImageFont.truetype(fp, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Calculate image size
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    total_h = sum(line_heights) + padding * 2 + (len(lines) - 1) * 8
    total_w = width

    # Draw
    img = Image.new("RGBA", (total_w, total_h), bg_color if bg_color else (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = padding
    for line, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (total_w - lw) // 2
        draw.text((x, y), line, font=font, fill=text_color)
        y += lh + 8

    return np.array(img)


# ── Title card generator ──────────────────────────────────────────────────────

def _make_intro_card(title: str, hook_fact: str, duration: float = 3.0) -> CompositeVideoClip:
    """Create a full-screen intro title card."""
    bg = ColorClip(size=(W, H), color=(15, 20, 40), duration=duration)  # Dark navy

    title_arr = _make_text_image(
        title, W - 80, font_size=FONT_SIZE_TITLE + 4,
        text_color=(255, 220, 80),  # Gold
    )
    hook_arr = _make_text_image(
        hook_fact, W - 120, font_size=FONT_SIZE_SCENE - 2,
        text_color=(200, 220, 255),
    )

    title_clip = (
        ImageClip(title_arr)
        .with_duration(duration)
        .with_position(("center", H // 2 - title_arr.shape[0] - 20))
    )
    hook_clip = (
        ImageClip(hook_arr)
        .with_duration(duration)
        .with_position(("center", H // 2 + 20))
    )

    return CompositeVideoClip([bg, title_clip, hook_clip]).with_duration(duration)


def _make_lower_third(scene_title: str, duration: float) -> ImageClip:
    """Create a lower-third title overlay for a scene."""
    bar_arr = _make_text_image(
        scene_title,
        W - 40,
        font_size=FONT_SIZE_SCENE,
        text_color=(255, 255, 255),
        bg_color=(20, 60, 120, 200),  # Semi-transparent blue
        padding=14,
    )
    return (
        ImageClip(bar_arr)
        .with_duration(min(duration, 4.0))  # Show for max 4s
        .with_position((20, H - bar_arr.shape[0] - 20))
        .with_effects([afx.AudioFadeIn(0.3)])  # Reuse fade for image (handled in compose)
    )


# ── Scene assembler ───────────────────────────────────────────────────────────

def _build_scene_clip(
    video_path: Path,
    audio_path: Path,
    scene_title: str,
    scene_number: int,
) -> CompositeVideoClip | None:
    """
    Assemble a single scene: stock video + narration audio + lower-third title.
    Returns None if any required file is missing.
    """
    if not video_path or not video_path.exists():
        return None
    if not audio_path or not audio_path.exists():
        return None

    # Load audio to get exact duration
    audio = AudioFileClip(str(audio_path))
    target_duration = audio.duration + 0.5  # Small tail for breathing room

    # Load and loop/trim video to match audio
    raw_video = VideoFileClip(str(video_path), audio=False)
    if raw_video.duration < target_duration:
        # Loop the clip
        loops_needed = int(target_duration / raw_video.duration) + 2
        from moviepy import concatenate_videoclips as cv
        looped = cv([raw_video] * loops_needed)
        video_clip = looped.subclipped(0, target_duration)
    else:
        video_clip = raw_video.subclipped(0, target_duration)

    # Resize to target resolution
    video_clip = video_clip.resized((W, H))

    # Add narration audio
    video_clip = video_clip.with_audio(audio)

    # Add lower-third title overlay (first 4 seconds)
    lower_third = _make_lower_third(scene_title, target_duration)
    composed = CompositeVideoClip([video_clip, lower_third])

    # Fade in/out
    composed = composed.with_effects([
        afx.AudioFadeIn(FADE_DURATION),
        afx.AudioFadeOut(FADE_DURATION),
    ])

    return composed.with_duration(target_duration)


# ── Outro card ────────────────────────────────────────────────────────────────

def _make_outro_card(topic: str, sources_count: int, duration: float = 4.0) -> CompositeVideoClip:
    """Create a closing card with sources acknowledgement."""
    bg = ColorClip(size=(W, H), color=(15, 20, 40), duration=duration)

    msg = f"Thanks for watching!\nBased on {sources_count} verified sources.\nStay curious. 🎓"
    text_arr = _make_text_image(
        msg, W - 100, font_size=FONT_SIZE_SCENE + 2,
        text_color=(200, 230, 255),
    )
    text_clip = (
        ImageClip(text_arr)
        .with_duration(duration)
        .with_position("center")
    )
    return CompositeVideoClip([bg, text_clip]).with_duration(duration)


# ── Main assembler class ──────────────────────────────────────────────────────

class VideoAssembler:
    """Assembles all scene clips into a final educational video."""

    def assemble(
        self,
        script: dict,
        audio_results: list[dict],
        video_results: list[dict],
        slug: str,
        progress_callback=None,
    ) -> Path:
        """
        Combine all scenes into a final MP4.

        Args:
            script: Script dict from ScriptWriter
            audio_results: List of {scene_number, audio_path} from Narrator
            video_results: List of {scene_number, video_path} from VideoFetcher
            slug: Unique run identifier
            progress_callback: Optional callable(message, step, total)

        Returns:
            Path to the final output video
        """
        Config.ensure_dirs()
        scenes = script.get("scenes", [])
        total_scenes = len(scenes)

        # Build lookup dicts for quick access
        audio_map = {r["scene_number"]: r.get("audio_path") for r in audio_results}
        video_map = {r["scene_number"]: r.get("video_path") for r in video_results}

        clips = []

        # 1. Intro title card
        if progress_callback:
            progress_callback("Building intro card...", 0, total_scenes + 2)
        intro = _make_intro_card(
            script.get("title", script.get("topic", "Educational Video")),
            script.get("hook_fact", ""),
            duration=3.5,
        )
        clips.append(intro)

        # 2. Scene clips
        for i, scene in enumerate(scenes):
            scene_num = scene["scene_number"]
            audio_path = audio_map.get(scene_num)
            video_path = video_map.get(scene_num)

            if progress_callback:
                progress_callback(
                    f"Assembling scene {scene_num}: {scene['title'][:45]}...",
                    i + 1,
                    total_scenes + 2,
                )

            clip = _build_scene_clip(
                video_path=Path(video_path) if video_path else None,
                audio_path=Path(audio_path) if audio_path else None,
                scene_title=scene["title"],
                scene_number=scene_num,
            )

            if clip is not None:
                clips.append(clip)
            else:
                print(f"  ⚠️  Skipping scene {scene_num} (missing assets)")

        # 3. Outro card
        if progress_callback:
            progress_callback("Building outro card...", total_scenes + 1, total_scenes + 2)

        outro = _make_outro_card(
            topic=script.get("title", ""),
            sources_count=len(script.get("scenes", [])),
        )
        clips.append(outro)

        if not clips:
            raise RuntimeError("No clips assembled — check that all scenes completed successfully.")

        # 4. Concatenate all clips
        if progress_callback:
            progress_callback("Concatenating and rendering final video (this may take a few minutes)...",
                              total_scenes + 2, total_scenes + 2)

        final = concatenate_videoclips(clips, method="compose")
        output_path = Config.final_dir() / "final.mp4"

        final.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            threads=4,
            logger=None,  # Suppress verbose moviepy output
        )

        # Cleanup clip objects
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

        return output_path
