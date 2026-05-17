"""Shared configuration loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")


class Config:
    # API Keys
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
    GOOGLE_AI_API_KEY: str = os.getenv("GOOGLE_AI_API_KEY", "")
    PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    TOGETHER_API_KEY: str = os.getenv("TOGETHER_API_KEY", "")

    # Pipeline
    DEFAULT_TIER: str = os.getenv("DEFAULT_TIER", "a")
    DEFAULT_VOICE: str = os.getenv("DEFAULT_VOICE", "en-US-GuyNeural")

    # Paths
    ROOT_DIR: Path = _root
    OUTPUT_DIR: Path = _root / os.getenv("OUTPUT_DIR", "outputs")

    # Video settings
    VIDEO_WIDTH: int = int(os.getenv("VIDEO_WIDTH", "1280"))
    VIDEO_HEIGHT: int = int(os.getenv("VIDEO_HEIGHT", "720"))
    TARGET_DURATION_SECONDS: int = int(os.getenv("TARGET_DURATION_SECONDS", "240"))

    # Derived output subdirs
    @classmethod
    def research_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "research"

    @classmethod
    def scripts_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "scripts"

    @classmethod
    def audio_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "audio"

    @classmethod
    def clips_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "clips"

    @classmethod
    def final_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "final"

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all output directories if they don't exist."""
        for d in [
            cls.research_dir(),
            cls.scripts_dir(),
            cls.audio_dir(),
            cls.clips_dir(),
            cls.final_dir(),
        ]:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls, tier: str) -> list[str]:
        """Return list of missing keys for the given tier."""
        missing = []
        if tier in ("a",):
            if not cls.TAVILY_API_KEY or "your-key" in cls.TAVILY_API_KEY:
                missing.append("TAVILY_API_KEY")
            if not cls.GROQ_API_KEY or "your-key" in cls.GROQ_API_KEY:
                missing.append("GROQ_API_KEY")
            if not cls.PEXELS_API_KEY or "your-key" in cls.PEXELS_API_KEY:
                missing.append("PEXELS_API_KEY")
        elif tier in ("b",):
            if not cls.PERPLEXITY_API_KEY:
                missing.append("PERPLEXITY_API_KEY")
        elif tier in ("c",):
            if not cls.GOOGLE_AI_API_KEY:
                missing.append("GOOGLE_AI_API_KEY")
        return missing
