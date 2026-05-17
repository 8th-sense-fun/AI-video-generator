# 🎬 NotebookLM Auto

**Automated research-to-video pipeline**: Enter any topic → get a cinematic, 101-style educational video.

Uses deep web research, AI scriptwriting, neural text-to-speech, and stock video to produce a polished MP4 — fully from the command line.

---

## 🗺️ Pipeline Overview

```
Topic Input (CLI)
    │
    ▼
🔍 Deep Research        (Tavily API — autonomous multi-query web research)
    │ research_report.md + sources.json
    ▼
✍️  Script Writer        (Groq / Llama 3.3 70B — cinematic scene-by-scene script)
    │ script.json + script.md
    ▼
🎙️  Narrator             (edge-tts — free Microsoft neural TTS, no API key)
    │ audio/scene_XX.mp3
    ▼
🎞️  Video Fetcher        (Pexels API — free HD stock footage)
    │ clips/scene_XX.mp4
    ▼
🎬 Assembler            (MoviePy + FFmpeg — compose, title cards, outro)
    │
    ▼
outputs/final/topic_YYYYMMDD_HHMMSS_final.mp4
```

---

## 💰 Cost Per Video

| Tier | Tools | Cost |
|------|-------|------|
| **A — Free (default)** | Tavily + Groq + edge-tts + Pexels + MoviePy | **~$0** |
| B — Low Cost *(coming soon)* | Perplexity + ElevenLabs + FLUX images | ~$1–3 |
| C — Premium *(coming soon)* | Gemini Deep Research + Gemini TTS + Veo 3.1 | ~$10–25 |

---

## ⚙️ Setup

### 1. Prerequisites

- Python 3.11+
- FFmpeg (required by MoviePy)

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 2. Clone & Install

```bash
git clone https://github.com/your-username/notebooklm-auto.git
cd notebooklm-auto

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

| Key | Get it from | Cost |
|-----|-------------|------|
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) | Free (1000 searches/mo) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Free (rate-limited) |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) | Free (20k req/mo) |

### 4. Verify Setup

```bash
python cli.py check
```

---

## 🚀 Usage

### Basic — Run full pipeline

```bash
python cli.py run --topic "US Housing Market"
```

### Custom voice & duration

```bash
python cli.py run --topic "Climate Change" --voice en-US-ChristopherNeural --duration 180
```

### List available voices

```bash
python cli.py list-voices
```

### Resume from cached research (saves API calls on re-runs)

```bash
# Skip research, re-run script + video
python cli.py run --topic "US Housing Market" \
  --skip-research outputs/research/us_housing_market_20260517_120000_sources.json

# Skip research AND script, only re-render video
python cli.py run --topic "US Housing Market" \
  --skip-research outputs/research/us_housing_market_20260517_120000_sources.json \
  --skip-script outputs/scripts/us_housing_market_20260517_120000.json
```

### Check config

```bash
python cli.py check
```

---

## 📁 Project Structure

```
notebooklm-auto/
├── cli.py                        # CLI entry point
├── requirements.txt
├── .env                          # Your API keys (gitignored)
├── .env.example                  # Template — commit this, not .env
├── .gitignore
├── README.md
│
├── src/
│   ├── config.py                 # Centralised config & env loading
│   ├── pipeline.py               # Orchestrator — wires all stages together
│   │
│   ├── research/
│   │   └── deep_research.py      # Tavily multi-query research + report builder
│   ├── script/
│   │   └── script_writer.py      # Groq/Llama → cinematic scene script
│   ├── audio/
│   │   └── narrator.py           # edge-tts neural voiceover per scene
│   ├── video/
│   │   ├── fetcher.py            # Pexels stock video downloader
│   │   └── assembler.py          # MoviePy final video assembly
│   └── utils/
│       └── helpers.py            # Slugify, formatting, shared utilities
│
├── outputs/                      # Generated files (gitignored)
│   ├── research/                 # .md reports + .json source lists
│   ├── scripts/                  # .json scripts + .md readable scripts
│   ├── audio/                    # Per-scene .mp3 narration files
│   ├── clips/                    # Per-scene raw stock video .mp4
│   └── final/                    # ✅ Final output videos
│
└── tests/
    └── test_pipeline.py          # Unit + smoke tests
```

---

## 🧪 Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## 🎨 Output Video Structure

Each generated video contains:

1. **Title card** (3.5s) — video title + hook fact, dark cinematic background
2. **Scene clips** (varies) — stock footage + neural voiceover + lower-third scene title
3. **Outro card** (4s) — closing message + source count

Typical video breakdown for a 4-minute video:
- ~8–10 scenes
- Each scene: 20–35 seconds
- No watermarks on the video output
- Audio: Neural US male voice (en-US-GuyNeural) at natural pace

---

## 🔊 Recommended Voices

| Voice | Style |
|-------|-------|
| `en-US-GuyNeural` | US male, warm and engaging **(default)** |
| `en-US-ChristopherNeural` | US male, authoritative / documentary |
| `en-US-EricNeural` | US male, casual / conversational |
| `en-GB-RyanNeural` | UK male, polished / BBC-style |
| `en-AU-WilliamNeural` | Australian male, relaxed |

Run `python cli.py list-voices` to see all 50+ options.

---

## 🔮 Upgrading Tiers (Future)

The architecture is designed to be upgradeable. To switch to a higher-quality tier:

1. Add the relevant API keys to `.env`
2. Run with `--tier b` or `--tier c`

Tier C (Gemini) will use:
- **Gemini Deep Research Max** for research (~$5–7/run)
- **Gemini 3 Flash** for script writing
- **Gemini TTS** for narration
- **Veo 3.1** for fully AI-generated video clips (no stock footage)

---

## ⚠️ Important Notes

- **API keys**: Never commit `.env` to git — it's in `.gitignore`
- **Pexels terms**: Stock videos are free for use but check [Pexels license](https://www.pexels.com/license/) for commercial use
- **Rate limits**: Groq free tier: 30 req/min; Pexels: 200 req/hour
- **Video length**: Rendering the final video (MoviePy step) can take 2–5 minutes depending on your machine

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
