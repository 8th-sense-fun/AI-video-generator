"""
Stock video fetcher — downloads clips from Pexels API (Tier A, free).

For each scene, searches Pexels using the scene's pexels_keywords,
downloads the best matching video clip, and trims it to match the
narration audio duration.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import Config


_PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"
_PEXELS_HEADERS = lambda: {"Authorization": Config.PEXELS_API_KEY}  # noqa: E731


# ── Pexels search ─────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _search_pexels(query: str, per_page: int = 15) -> list[dict]:
    """Search Pexels for videos matching a query string. Returns list of video objects."""
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": "landscape",
        "size": "medium",
    }
    resp = requests.get(_PEXELS_VIDEO_SEARCH, headers=_PEXELS_HEADERS(), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("videos", [])


def _pick_best_video(videos: list[dict], used_ids: set, min_duration: int = 10) -> dict | None:
    """
    Pick the best unused video from results.
    Prefers HD, minimum duration, and clips not already used in this run.
    NEVER allows repeating a previously used video ID.
    """
    # Always filter out already-used video IDs — no fallback to repeats
    fresh = [v for v in videos if v.get("id") not in used_ids]

    candidates = [v for v in fresh if v.get("duration", 0) >= min_duration]
    if not candidates:
        candidates = fresh  # Relax duration requirement but still no repeats

    if not candidates:
        return None

    # Pick a random one from top 5 for variety
    return random.choice(candidates[:5])


def _get_download_url(video: dict, preferred_quality: str = "hd") -> str | None:
    """Extract the best download URL from a Pexels video object."""
    files = video.get("video_files", [])
    # Prefer HD landscape
    hd_files = [
        f for f in files
        if f.get("quality") == preferred_quality and f.get("width", 0) >= 1280
    ]
    if hd_files:
        return hd_files[0]["link"]
    # Fallback to any file
    if files:
        return files[0]["link"]
    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def _download_file(url: str, output_path: Path) -> None:
    """Download a file from URL to output_path with streaming."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)


# ── Main fetcher class ────────────────────────────────────────────────────────

class VideoFetcher:
    """Tier A video provider using Pexels (free stock footage)."""

    def __init__(self) -> None:
        pass  # API key loaded from Config in headers lambda

    def fetch_for_script(
        self,
        script: dict,
        slug: str,
        progress_callback=None,
    ) -> list[dict]:
        """
        Download stock video clips for all scenes in the script.

        Args:
            script: Output from ScriptWriter.write()
            slug: Unique run identifier for filenames
            progress_callback: Optional callable(message, step, total)

        Returns:
            List of dicts with scene_number and video_path (or None if failed)
        """
        scenes = script.get("scenes", [])
        results = []
        used_video_ids: set = set()  # Track used Pexels IDs to prevent cross-scene repeats

        for i, scene in enumerate(scenes):
            scene_num = scene["scene_number"]
            # Prefer the specific search query the LLM crafted; fall back to keywords
            search_query = scene.get("pexels_search_query") or " ".join(scene.get("pexels_keywords", ["nature"])[:3])
            keywords = scene.get("pexels_keywords", ["nature"])
            duration_hint = scene.get("duration_hint", 20)

            if progress_callback:
                progress_callback(
                    f"Fetching video: Scene {scene_num} — \"{search_query[:50]}\"",
                    i + 1,
                    len(scenes),
                )

            video_path = Config.clips_dir() / f"scene_{scene_num:02d}_raw.mp4"

            # Skip if already downloaded
            if video_path.exists() and video_path.stat().st_size > 10_000:
                results.append({"scene_number": scene_num, "video_path": video_path})
                continue

            try:
                # Build a list of progressively broader fallback queries
                fallback_queries = [search_query]
                if keywords:
                    fallback_queries.append(" ".join(keywords[:3]))
                    fallback_queries.append(keywords[0])
                    if len(keywords) > 1:
                        fallback_queries.append(keywords[1])
                # Last resort: very generic terms related to geography/travel
                fallback_queries += ["city landmark aerial", "nature landscape scenic", "travel destination"]

                best = None
                for attempt_query in fallback_queries:
                    videos = _search_pexels(attempt_query, per_page=20)
                    if videos:
                        best = _pick_best_video(videos, used_video_ids, min_duration=duration_hint)
                        if best:
                            break  # Found a fresh, unique clip

                if not best:
                    raise RuntimeError(f"No unique Pexels clip found after all fallbacks for: {search_query!r}")

                # Record this video ID so no other scene reuses it
                used_video_ids.add(best["id"])

                url = _get_download_url(best)
                if not url:
                    raise RuntimeError("Could not find download URL")

                _download_file(url, video_path)
                results.append({"scene_number": scene_num, "video_path": video_path})

            except Exception as exc:
                print(f"  ⚠️  Scene {scene_num} video fetch failed: {exc}")
                results.append({"scene_number": scene_num, "video_path": None, "error": str(exc)})

            # Polite rate limiting — Pexels allows 200 req/hour
            time.sleep(0.5)

        return results
