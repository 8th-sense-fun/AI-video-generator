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

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

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

STRUCTURE (adapt scene count to fit 3–5 minute target):
1. Hook / Opening (grab attention with a surprising fact or relatable scenario)
2. Foundation (explain the basics from scratch)
3. Key Factors (2–4 scenes on the main drivers/causes)
4. Current State (what's happening right now, with data)
5. Impact on People (make it personal and relatable)
6. Future Outlook (what experts say is coming)
7. Closing / Call to Action (what viewers can do or take away)

OUTPUT FORMAT — respond with ONLY valid JSON, no markdown fences, no commentary:
{
  "title": "string — full video title",
  "hook_fact": "string — one surprising fact for the thumbnail/intro",
  "total_estimated_seconds": number,
  "scenes": [
    {
      "scene_number": 1,
      "title": "string",
      "narration": "string — full spoken narration text (50–120 words per scene)",
      "visual_description": "string — describe what should be shown on screen",
      "pexels_keywords": ["keyword1", "keyword2", "keyword3"],
      "duration_hint": number
    }
  ]
}
"""

# ── Groq call ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _call_groq(client: Groq, research_report: str, topic: str, target_seconds: int) -> str:
    """Call Groq API and return raw response text."""
    user_prompt = f"""
Topic: {topic}
Target video duration: {target_seconds} seconds ({target_seconds // 60}–{target_seconds // 60 + 1} minutes)

Research Report:
{research_report[:12000]}

Write the complete cinematic educational video script as JSON.
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
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


# ── Main script writer class ───────────────────────────────────────────────────

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

        if progress_callback:
            progress_callback("Writing cinematic video script with Llama 3.3...", 1, 1)

        raw = _call_groq(self.client, report, topic, target)

        try:
            script = _extract_json(raw)
            _validate_script(script)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Script parsing failed: {exc}\n\nRaw response:\n{raw[:500]}") from exc

        # Ensure duration_hint defaults
        for scene in script["scenes"]:
            if "duration_hint" not in scene or not scene["duration_hint"]:
                # Estimate ~1.5 words per second for narration
                word_count = len(scene["narration"].split())
                scene["duration_hint"] = max(15, int(word_count / 1.5))

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
