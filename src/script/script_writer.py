"""
Script writer — converts a research report into a structured cinematic
scene-by-scene video script using Groq (Llama 3.3 70B).

Each scene contains:
  - scene_number: int
  - title: str  (e.g. "What Is the US Housing Market?")
  - narration: str  (what the voiceover will say — plain spoken English)
  - visual_description: str  (what to show / search for on Pexels)
  - pexels_keywords: list[str]  (search terms for stock video)
  - duration_hint: int  (approximate seconds for this scene)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import Config

# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an award-winning documentary scriptwriter and educator.
Your task is to transform a research report into a compelling, cinematic,
"101-style" educational video script that anyone — regardless of background —
can understand and enjoy.

STYLE GUIDELINES:
- Tone: Warm, engaging, confident — like a knowledgeable friend explaining over coffee
- Vocabulary: Simple, clear — no unexplained jargon. If a term is used, define it immediately.
- Pacing: Build from "What is it?" → "Why does it matter?" → "What's happening now?" → "What does this mean for YOU?"
- Cinematic: Each scene should paint a vivid picture in the viewer's mind
- Educational: Every scene teaches ONE clear idea

STRUCTURE (adapt scene count to fit target — see user prompt):
- If the topic is a LIST or RANKING (e.g. "top 10", "best 5", "most visited", "ranking of"):
    • Dedicate ONE scene per list item. Each scene title = the item name/rank.
    • pexels_search_query MUST name the specific subject (e.g. "Eiffel Tower Paris",
      "Great Wall of China aerial", "Machu Picchu Peru mountains") — NEVER generic travel words.
- For all other topics, use a natural narrative arc:
    1. Hook / Opening (surprising fact or relatable scenario)
    2. Foundation (explain basics from scratch)
    3. Key Factors (2–4 scenes on main drivers — more for longer videos)
    4. Current State (data and what's happening now)
    5. Impact on People (personal and relatable)
    6. Future Outlook (what experts say is coming)
    7. Closing / Call to Action

VISUAL SEARCH RULES (apply to ALL topics):
- pexels_search_query must be a SPECIFIC, DESCRIPTIVE phrase that would return unique footage.
  ✅ Good: "aerial view Tokyo skyline night", "Federal Reserve building Washington DC",
           "surgeon performing operation close-up", "electric vehicle charging station"
  ❌ Bad:  "technology", "economy", "travel", "people", "world"
- Every scene must have a DIFFERENT pexels_search_query — never reuse the same query.
- Think like a video editor: what exact shot would you cut to for this moment?

OUTPUT FORMAT — respond with ONLY valid JSON, no markdown fences, no commentary:
{
  "title": "string — full video title",
  "hook_fact": "string — one surprising fact for the thumbnail/intro",
  "total_estimated_seconds": number,
  "scenes": [
    {
      "scene_number": 1,
      "title": "string",
      "narration": "string — full spoken narration text (target words per scene provided in user prompt)",
      "visual_description": "string — describe what should be shown on screen",
      "pexels_search_query": "string — specific Pexels search phrase for unique footage",
      "pexels_keywords": ["keyword1", "keyword2", "keyword3"],
      "duration_hint": number
    }
  ]
}
"""

# ── Groq call ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=60, max=120))
def _call_groq(
    client: Groq,
    research_report: str,
    topic: str,
    target_seconds: int,
    scene_count: int = 0,
) -> str:
    """Call Groq API and return raw response text."""
    # ~2.5 spoken words per second is a natural narration pace.
    # Each scene must fill (target_seconds / scene_count) seconds of real audio.
    effective_scenes = scene_count if scene_count > 0 else max(6, target_seconds // 30)
    seconds_per_scene = target_seconds // effective_scenes
    # Target a tight window: 2.4–2.8 words/sec so the total lands close to target_seconds
    min_words_per_scene = int(seconds_per_scene * 2.4)
    max_words_per_scene = int(seconds_per_scene * 2.8)

    scene_instruction = (
        f"IMPORTANT: Generate EXACTLY {scene_count} scenes."
        if scene_count > 0
        else f"Generate approximately {effective_scenes} scenes to fill the target duration."
    )

    user_prompt = f"""
Topic: {topic}
Target video duration: {target_seconds} seconds (~{target_seconds // 60} minutes)
{scene_instruction}

⚠️  NARRATION LENGTH — STRICT WORD COUNT RANGE (MANDATORY):
Each scene's "narration" field MUST contain between {min_words_per_scene} and {max_words_per_scene} words — no fewer, no more.
Each scene fills ~{seconds_per_scene} seconds of audio at a natural speaking pace (~2.5 words/sec).
- {min_words_per_scene} words ≈ {min_words_per_scene/2.5:.0f}s of audio (minimum)
- {max_words_per_scene} words ≈ {max_words_per_scene/2.5:.0f}s of audio (maximum)
Write full, flowing, vivid spoken paragraphs — not bullet points. Stay within the word count range.
If every scene hits ~{(min_words_per_scene+max_words_per_scene)//2} words, the total video will be approximately {target_seconds} seconds.

Research Report (summary):
{research_report[:4000]}

Write the complete cinematic educational video script as JSON.
"""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",   # 30k TPM free limit vs 6k for 70b
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2500,
    )
    return response.choices[0].message.content


# ── JSON extraction / validation ───────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Extract JSON from LLM response, handling common formatting issues."""
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    raw = raw.strip("`").strip()

    # Find first { and last }
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(raw[start:end])


def _validate_script(script: dict) -> None:
    """Raise ValueError if script is missing required fields."""
    required = ["title", "scenes"]
    for field in required:
        if field not in script:
            raise ValueError(f"Script missing required field: {field}")

    for i, scene in enumerate(script["scenes"]):
        for field in ["scene_number", "title", "narration", "visual_description", "pexels_keywords"]:
            if field not in scene:
                raise ValueError(f"Scene {i+1} missing field: {field}")
        # Backfill pexels_search_query from keywords if LLM omitted it
        if not scene.get("pexels_search_query"):
            scene["pexels_search_query"] = " ".join(scene["pexels_keywords"][:3])


# ── Narration expander (used when LLM returns too-short scenes) ───────────────

@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=60, max=120))
def _expand_narration(client: Groq, scene: dict, topic: str, target_words: int) -> str:
    """
    Ask the LLM to rewrite a single scene's narration to meet the minimum word count.
    Returns the expanded narration string.
    """
    prompt = f"""You are a documentary narrator. Rewrite the following scene narration so it is 
AT LEAST {target_words} words long. Keep the same topic, tone, and facts — just write more 
fully, add vivid details, context, and engaging storytelling. Output ONLY the narration text, 
no JSON, no labels.

Scene title: {scene['title']}
Topic: {topic}
Current narration ({len(scene['narration'].split())} words — too short):
{scene['narration']}
"""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


# ── Main script writer class ───────────────────────────────────────────────────

# ── List/ranking topic detector ───────────────────────────────────────────────

def _detect_list_count(topic: str) -> Optional[int]:
    """
    If the topic is a ranking or list (e.g. 'Top 10 ...', 'Best 5 ...', '10 Most ...'),
    return the list size so we can force exactly that many item-scenes.
    Returns None for non-list topics.
    """
    # Match patterns like "10", "top 10", "best 10", "10 most", "10 greatest", etc.
    patterns = [
        r'\btop[\s\-]?(\d+)\b',          # "top 10", "top-10"
        r'\bbest[\s\-]?(\d+)\b',          # "best 5"
        r'\b(\d+)[\s\-]?most\b',          # "10 most"
        r'\b(\d+)[\s\-]?best\b',          # "10 best"
        r'\b(\d+)[\s\-]?greatest\b',      # "10 greatest"
        r'\branking of[\s\-]?(\d+)\b',    # "ranking of 10"
        r'\b(\d+)[\s\-]?(?:places|cities|countries|things|ways|tips|facts|reasons|wonders)\b',
    ]
    for pattern in patterns:
        m = re.search(pattern, topic, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 2 <= n <= 30:  # sanity bounds
                return n
    return None


class ScriptWriter:
    """Tier A script writer using Groq (Llama 3.3 70B)."""

    def __init__(self) -> None:
        self.client = Groq(api_key=Config.GROQ_API_KEY)

    def write(
        self,
        research_data: dict,
        progress_callback=None,
    ) -> dict:
        """
        Convert research data into a structured video script.

        Args:
            research_data: Output from DeepResearcher.research()
            progress_callback: Optional callable(message, step, total)

        Returns:
            Parsed script dict with title, scenes, etc.
        """
        topic = research_data["topic"]
        report = research_data["full_report"]
        target = Config.TARGET_DURATION_SECONDS
        scene_count = Config.TARGET_SCENE_COUNT  # 0 = auto

        # ── Auto-detect list/ranking topics and force one scene per item ──────
        list_n = _detect_list_count(topic)
        if list_n is not None and scene_count == 0:
            # 1 intro scene + N item scenes + 1 outro scene
            scene_count = list_n + 2
            # Also widen the target duration so each item gets enough airtime
            # (at least 25s per item scene, plus 15s each for intro/outro)
            min_target = list_n * 25 + 30
            target = max(target, min_target)
            if progress_callback:
                progress_callback(
                    f"📋 Detected list topic with {list_n} items → forcing {scene_count} scenes "
                    f"(1 per item + intro/outro), target={target}s",
                    1, 1,
                )

        effective_scenes = scene_count if scene_count > 0 else max(6, target // 30)
        seconds_per_scene = target // effective_scenes
        min_words = int(seconds_per_scene * 2.4)   # must match _call_groq logic
        max_words = int(seconds_per_scene * 2.8)

        if progress_callback:
            progress_callback("Writing cinematic video script with Llama 3.3...", 1, 1)

        raw = _call_groq(self.client, report, topic, target, scene_count)

        try:
            script = _extract_json(raw)
            _validate_script(script)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Script parsing failed: {exc}\n\nRaw response:\n{raw[:500]}") from exc

        # ── Word-count guard: fix scenes outside the target range ────────────
        short_scenes = [
            s for s in script["scenes"]
            if len(s["narration"].split()) < min_words
        ]
        if short_scenes:
            if progress_callback:
                progress_callback(
                    f"⚠️  {len(short_scenes)} scene(s) too short — expanding narrations...", 1, 1
                )
            for scene in short_scenes:
                scene["narration"] = _expand_narration(
                    self.client, scene=scene, topic=topic, target_words=min_words
                )

        # Trim any scenes that ran over max_words (keep last max_words words of narration)
        for scene in script["scenes"]:
            words = scene["narration"].split()
            if len(words) > max_words:
                scene["narration"] = " ".join(words[:max_words])

        # Recalculate duration_hint from actual narration word count
        for scene in script["scenes"]:
            word_count = len(scene["narration"].split())
            # ~2.5 words/sec is a natural spoken pace
            scene["duration_hint"] = max(15, int(word_count / 2.5))

            # Ensure pexels_keywords is a list
            if isinstance(scene["pexels_keywords"], str):
                scene["pexels_keywords"] = [scene["pexels_keywords"]]

        return script

    def save(self, script: dict, slug: str) -> Path:
        """Save script to disk as .json and .md files."""
        Config.ensure_dirs()
        json_path = Config.scripts_dir() / "script.json"
        json_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

        md_path = Config.scripts_dir() / "script.md"
        md_path.write_text(_script_to_markdown(script), encoding="utf-8")

        return json_path


def _script_to_markdown(script: dict) -> str:
    """Convert script dict to human-readable markdown."""
    lines = [
        f"# {script.get('title', 'Untitled Video')}",
        f"\n*Hook fact: {script.get('hook_fact', '')}*",
        f"\n*Estimated duration: ~{script.get('total_estimated_seconds', 0) // 60} minutes*\n",
        "---\n",
    ]
    for scene in script.get("scenes", []):
        lines += [
            f"## Scene {scene['scene_number']}: {scene['title']}",
            f"**Duration:** ~{scene.get('duration_hint', '?')}s",
            f"\n**Narration:**\n> {scene['narration']}",
            f"\n**Visual:** {scene['visual_description']}",
            f"\n**Pexels Keywords:** {', '.join(scene.get('pexels_keywords', []))}",
            "\n---\n",
        ]
    return "\n".join(lines)
