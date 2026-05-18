# NotebookLM Auto 🎬

> **Automatically research any topic and generate a cinematic educational video — entirely with free APIs.**

Type a topic. Get a polished MP4 in minutes.

---

## What It Does

NotebookLM Auto is an end-to-end AI pipeline that:

1. **Researches** your topic using Tavily's deep web search
2. **Writes** a scene-by-scene documentary-style script via Groq (Llama 3.3 70B)
3. **Narrates** each scene with edge-tts (Microsoft neural voices, 100% free)
4. **Fetches** matching stock video clips from Pexels
5. **Assembles** everything into a final `.mp4` with intro card, lower-thirds, crossfades, and an outro

All Tier A services are **free**. No OpenAI, no paid TTS, no paid video stock subscription needed.

---

## Quick Start

### 1. Clone & Install

```bash
git clone <repo-url>
cd NotebookLM_auto
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env and fill in the three required keys
```

| Key | Service | Free tier |
|-----|---------|-----------|
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) | ✅ 1,000 searches/month |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | ✅ Generous free tier |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) | ✅ Free for individuals |

### 3. Run

```bash
python cli.py run --topic "The Rise of Electric Vehicles"
```

The final video is saved to `outputs/<run-id>/final/final.mp4` and opened automatically on macOS.

---

## Standard Operating Procedure (SOP)

### Full pipeline run

```bash
python cli.py run --topic "TOPIC HERE"
```

### Common options

```bash
# Specify voice (default: en-US-GuyNeural)
python cli.py run --topic "Solar Energy" --voice en-US-ChristopherNeural

# Set target duration (default: 240s = 4 min)
python cli.py run --topic "Solar Energy" --duration 300

# Fix scene count (default: auto from duration)
python cli.py run --topic "Top 10 World Wonders" --scenes 12

# Change visual complexity preset
python cli.py run --topic "Solar Energy" --complexity cinematic

# Skip research (reuse existing sources.json)
python cli.py run --topic "Solar Energy" --skip-research outputs/solar_energy_20260517_120000

# Skip research AND script (reuse both, re-render video)
python cli.py run --topic "Solar Energy" \
  --skip-research outputs/solar_energy_20260517_120000 \
  --skip-script  outputs/solar_energy_20260517_120000
```

### Check your config

```bash
python cli.py check
```

### List available TTS voices

```bash
python cli.py list-voices
```

### Typical run time

| Stage | Typical duration |
|-------|-----------------|
| Research (5 Tavily queries) | 15–30 s |
| Script writing (Groq LLM) | 10–20 s |
| Narration (edge-tts, 10 scenes) | 30–60 s |
| Stock video fetch (Pexels) | 20–40 s |
| Assembly (MoviePy render) | 2–5 min |
| **Total** | **~4–6 min** |

---

## Output Folder Structure

Each run creates a self-contained folder under `outputs/`:

```
outputs/
└── solar_energy_20260517_130000/
    ├── research/
    │   ├── sources.json       ← raw search results
    │   └── report.md          ← human-readable research report
    ├── scripts/
    │   └── script.json        ← structured scene-by-scene script
    ├── audio/
    │   ├── scene_01.mp3       ← per-scene narration
    │   └── scene_02.mp3
    ├── clips/
    │   ├── scene_01.mp4       ← downloaded stock video
    │   └── scene_02.mp4
    └── final/
        └── final.mp4          ← ✅ the finished video
```

Use `--skip-research` or `--skip-script` to point at an existing folder and skip expensive API calls when iterating.

---

## Codebase Overview

```
NotebookLM_auto/
├── cli.py                    ← Click CLI entry point
├── src/
│   ├── config.py             ← All settings, paths, env vars
│   ├── pipeline.py           ← Stage orchestrator
│   ├── research/
│   │   └── deep_research.py  ← Tavily multi-query researcher
│   ├── script/
│   │   └── script_writer.py  ← Groq LLM script writer
│   ├── audio/
│   │   ├── narrator.py       ← edge-tts per-scene narration
│   │   └── music.py          ← stub (reserved for future use)
│   ├── video/
│   │   ├── fetcher.py        ← Pexels stock video downloader
│   │   └── assembler.py      ← MoviePy final render
│   └── utils/
│       └── helpers.py        ← slugify, run_slug, formatting
├── tests/
│   └── test_pipeline.py
└── outputs/                  ← All run artifacts (git-ignored)
```

### Data Flow

```
topic (str)
    │
    ▼ Step 1 — DeepResearcher
    research_data: {topic, sources: [{title, url, content, score}], report_md}
    │
    ▼ Step 2 — ScriptWriter
    script: {title, hook_fact, scenes: [{scene_number, title, narration,
             visual_description, pexels_keywords, duration_hint}]}
    │
    ├─▶ Step 3 — Narrator          → audio_results: [{scene_number, audio_path}]
    │
    └─▶ Step 4 — VideoFetcher      → video_results: [{scene_number, video_path}]
                    │
                    ▼ Step 5 — VideoAssembler
                    final.mp4
```

---

## Module Deep-Dive

### `src/config.py`

Central configuration hub. Reads from environment variables and `.env`.

Key class variables:
- `TAVILY_API_KEY`, `GROQ_API_KEY`, `PEXELS_API_KEY` — API credentials
- `TARGET_DURATION_SECONDS` — target video length (default 240)
- `TARGET_SCENE_COUNT` — 0 = auto-calculated by LLM
- `COMPLEXITY` — `simple | normal | cinematic` — controls fade duration, Ken Burns, lower-third timing
- `set_run(slug)` — must be called before any directory methods; scopes all output dirs under `outputs/<slug>/`

### `src/research/deep_research.py`

Fires **5 parallel sub-queries** to Tavily for comprehensive topic coverage (overview, statistics, causes, forecast, beginner guide). Each query returns up to 5 results with full raw content. Content is cleaned of HTML, deduplicated by URL, and scored by relevance. The top sources are assembled into a markdown report.

### `src/script/script_writer.py`

Sends the research report to **Groq (Llama 3.3 70B)** with a detailed system prompt that enforces documentary-style writing. Handles two structural templates automatically:
- **List/Ranking topics** (e.g. "Top 10 Most Visited Places"): one scene per item, specific Pexels query per location
- **Narrative topics**: Hook → Foundation → Factors → Current State → Impact → Future → CTA

The LLM response is JSON; robust fallback parsing handles malformed responses.

### `src/audio/narrator.py`

Uses **edge-tts** (free Microsoft neural TTS) to synthesize each scene's narration text to an MP3 file. Runs scenes sequentially. Supports any edge-tts voice name (e.g. `en-US-GuyNeural`, `en-US-ChristopherNeural`, `en-GB-SoniaNeural`).

### `src/video/fetcher.py`

Queries the **Pexels API** with each scene's `pexels_keywords` list. Tries multiple keyword variants until a suitable clip is found. Downloads the best-matching free video to `clips/scene_NN.mp4`. Falls back gracefully — scenes without a clip are skipped during assembly with a warning.

### `src/video/assembler.py`

The most complex module. Uses **MoviePy** to:

1. **Intro card** — full-screen navy/gold title card with topic and hook fact
2. **Per-scene clip** — for each scene:
   - Load stock video, stretch/loop intelligently to match narration duration
   - Resize to `1280×720`
   - Attach narration audio
   - Overlay lower-third title bar (semi-transparent blue, PIL-rendered text)
   - Apply fade-in / fade-out (duration from complexity preset)
3. **Outro card** — closing message with sources count
4. Concatenate all clips with `method="compose"` and render to `final.mp4` via `libx264 + AAC`

The `_stretch_clip_to_duration` function handles short clips intelligently: if a clip is ≥55% of needed duration, it applies a slow Ken Burns zoom; if shorter, it builds non-overlapping random sub-segments from different parts of the clip to avoid obvious looping.

---

## Configuration Reference (`.env`)

```dotenv
# Required
TAVILY_API_KEY=tvly-...
GROQ_API_KEY=gsk_...
PEXELS_API_KEY=...

# Optional overrides
DEFAULT_VOICE=en-US-GuyNeural
TARGET_DURATION_SECONDS=240
TARGET_SCENE_COUNT=0          # 0 = auto
COMPLEXITY=normal             # simple | normal | cinematic
VIDEO_WIDTH=1280
VIDEO_HEIGHT=720
OUTPUT_DIR=outputs
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Missing API keys` error | Run `python cli.py check` and fill in `.env` |
| Some scenes skipped in output | Pexels returned no results — broaden the topic or run again |
| Narration is cut off | Increase `TARGET_DURATION_SECONDS` |
| Video render very slow | Normal — MoviePy encodes in real time. 4-min video ≈ 3–5 min render. |
| `Config.set_run() must be called` | Don't import pipeline modules before calling `Pipeline.run()` |
| Script JSON parse error | Groq occasionally returns malformed JSON; the writer retries automatically |

---

## License

MIT — see `LICENSE`.
