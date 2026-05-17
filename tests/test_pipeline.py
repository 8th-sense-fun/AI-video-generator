"""
Unit tests for the NotebookLM Auto pipeline.

Run with:  pytest tests/ -v
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── Helpers / fixtures ────────────────────────────────────────────────────────

MOCK_TOPIC = "US Housing Market"

MOCK_RESEARCH_DATA = {
    "topic": MOCK_TOPIC,
    "timestamp": "2026-01-01T00:00:00",
    "sources": [
        {"title": "Housing Overview", "url": "https://example.com/1", "content": "...", "score": 0.9, "query": "test"},
        {"title": "Market Trends", "url": "https://example.com/2", "content": "...", "score": 0.8, "query": "test"},
    ],
    "summary_blocks": ["**Overview**\nThe US housing market is experiencing..."],
    "full_report": "# Research Report: US Housing Market\n\nTest content.",
}

MOCK_SCRIPT = {
    "title": "US Housing Market 101: Everything You Need to Know",
    "hook_fact": "Home prices rose 40% in just 3 years.",
    "total_estimated_seconds": 240,
    "scenes": [
        {
            "scene_number": 1,
            "title": "What is the Housing Market?",
            "narration": "Every year, millions of Americans buy and sell homes. But what exactly is the housing market and why does it matter to all of us?",
            "visual_description": "Aerial view of a suburban neighborhood with houses",
            "pexels_keywords": ["suburban houses", "neighborhood aerial", "real estate"],
            "duration_hint": 20,
        },
        {
            "scene_number": 2,
            "title": "Why Prices Are So High",
            "narration": "Over the past few years, home prices skyrocketed. The main reason? Not enough homes being built to meet growing demand.",
            "visual_description": "Construction site with workers building houses",
            "pexels_keywords": ["house construction", "building homes", "real estate"],
            "duration_hint": 22,
        },
    ],
}


# ── Config tests ──────────────────────────────────────────────────────────────

class TestConfig:
    def test_validate_missing_keys(self):
        from src.config import Config
        # Should detect placeholder keys
        with patch.object(Config, "TAVILY_API_KEY", "your-key-here"):
            missing = Config.validate("a")
            assert "TAVILY_API_KEY" in missing

    def test_ensure_dirs_creates_directories(self, tmp_path):
        from src.config import Config
        with patch.object(Config, "OUTPUT_DIR", tmp_path / "outputs"):
            Config.ensure_dirs()
            assert (tmp_path / "outputs" / "research").exists()
            assert (tmp_path / "outputs" / "final").exists()


# ── Utils tests ────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_slugify_basic(self):
        from src.utils.helpers import slugify
        assert slugify("US Housing Market 2026!") == "us_housing_market_2026"

    def test_slugify_special_chars(self):
        from src.utils.helpers import slugify
        result = slugify("AI & Machine Learning: A Guide")
        assert " " not in result
        assert "&" not in result
        assert ":" not in result

    def test_slugify_max_length(self):
        from src.utils.helpers import slugify
        long_topic = "A" * 200
        assert len(slugify(long_topic)) <= 50

    def test_run_slug_format(self):
        from src.utils.helpers import run_slug
        slug = run_slug("US Housing Market")
        assert slug.startswith("us_housing_market")
        assert len(slug) > 10

    def test_format_duration(self):
        from src.utils.helpers import format_duration
        assert format_duration(90) == "1:30"
        assert format_duration(65) == "1:05"
        assert format_duration(3600) == "60:00"


# ── Research tests ─────────────────────────────────────────────────────────────

class TestDeepResearcher:
    def test_build_queries(self):
        from src.research.deep_research import _build_queries
        queries = _build_queries("US Housing Market")
        assert len(queries) >= 4
        assert all("US Housing Market" in q for q in queries)

    def test_clean_content_strips_html(self):
        from src.research.deep_research import _clean_content
        html = "<p>Hello <b>world</b></p>"
        result = _clean_content(html)
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_clean_content_truncates(self):
        from src.research.deep_research import _clean_content
        long_text = "word " * 5000
        result = _clean_content(long_text, max_chars=100)
        assert len(result) <= 100

    def test_clean_content_empty(self):
        from src.research.deep_research import _clean_content
        assert _clean_content(None) == ""
        assert _clean_content("") == ""

    def test_build_report_structure(self):
        from src.research.deep_research import _build_report
        report = _build_report(MOCK_TOPIC, MOCK_RESEARCH_DATA["sources"], MOCK_RESEARCH_DATA["summary_blocks"])
        assert "US Housing Market" in report
        assert "Housing Overview" in report
        assert "example.com" in report


# ── Script writer tests ────────────────────────────────────────────────────────

class TestScriptWriter:
    def test_extract_json_clean(self):
        from src.script.script_writer import _extract_json
        raw = '{"title": "Test", "scenes": []}'
        result = _extract_json(raw)
        assert result["title"] == "Test"

    def test_extract_json_with_markdown_fence(self):
        from src.script.script_writer import _extract_json
        raw = '```json\n{"title": "Test", "scenes": []}\n```'
        result = _extract_json(raw)
        assert result["title"] == "Test"

    def test_extract_json_invalid(self):
        from src.script.script_writer import _extract_json
        with pytest.raises(ValueError):
            _extract_json("This is not JSON at all.")

    def test_validate_script_valid(self):
        from src.script.script_writer import _validate_script
        _validate_script(MOCK_SCRIPT)  # Should not raise

    def test_validate_script_missing_field(self):
        from src.script.script_writer import _validate_script
        with pytest.raises(ValueError):
            _validate_script({"title": "Test"})  # Missing "scenes"

    def test_script_to_markdown(self):
        from src.script.script_writer import _script_to_markdown
        md = _script_to_markdown(MOCK_SCRIPT)
        assert "US Housing Market 101" in md
        assert "Scene 1" in md
        assert "What is the Housing Market?" in md


# ── Narrator tests ─────────────────────────────────────────────────────────────

class TestNarrator:
    @patch("src.audio.narrator.synthesize_scene")
    def test_narrate_script_calls_per_scene(self, mock_synth, tmp_path):
        from src.audio.narrator import Narrator
        from src.config import Config

        mock_synth.return_value = tmp_path / "test.mp3"

        with patch.object(Config, "audio_dir", return_value=tmp_path):
            Config.ensure_dirs = lambda: None
            narrator = Narrator(voice="en-US-GuyNeural")
            results = narrator.narrate_script(MOCK_SCRIPT, "test_slug")

        assert len(results) == len(MOCK_SCRIPT["scenes"])
        assert mock_synth.call_count == len(MOCK_SCRIPT["scenes"])


# ── Integration smoke test ─────────────────────────────────────────────────────

class TestPipelineSmoke:
    """Smoke tests that verify pipeline wiring without real API calls."""

    def test_pipeline_instantiation(self):
        from src.pipeline import Pipeline
        p = Pipeline(tier="a")
        assert p.tier == "a"

    def test_pipeline_gets_researcher(self):
        from src.pipeline import Pipeline
        p = Pipeline(tier="a")
        researcher = p._get_researcher()
        assert researcher is not None

    def test_pipeline_gets_script_writer(self):
        from src.pipeline import Pipeline
        p = Pipeline(tier="a")
        writer = p._get_script_writer()
        assert writer is not None
