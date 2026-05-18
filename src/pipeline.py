"""
Pipeline orchestrator — coordinates all stages of the research-to-video pipeline.

Stage order:
  1. Research   (Tavily deep search → markdown report)
  2. Script     (Groq Llama 3.3 → scene-by-scene JSON script)
  3. Narration  (edge-tts → per-scene MP3 files)
  4. Video      (Pexels API → per-scene MP4 clips)
  5. Assemble   (MoviePy → final output MP4)
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from src.config import Config
from src.utils.helpers import run_slug, print_sources_table

console = Console()


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


class Pipeline:
    """
    End-to-end pipeline: Research → Script → Audio → Video → Assemble.

    Tier A (default, free): Tavily + Groq + edge-tts + Pexels + MoviePy
    """

    def __init__(self, tier: str = "a") -> None:
        self.tier = tier.lower()

    # ── Component factories ───────────────────────────────────────────────────

    def _get_researcher(self):
        if self.tier == "a":
            from src.research.deep_research import DeepResearcher
            return DeepResearcher()
        raise NotImplementedError(f"Tier '{self.tier}' researcher not implemented.")

    def _get_script_writer(self):
        from src.script.script_writer import ScriptWriter
        return ScriptWriter()

    def _get_narrator(self, voice: str | None = None):
        from src.audio.narrator import Narrator
        return Narrator(voice=voice)

    def _get_video_fetcher(self):
        if self.tier == "a":
            from src.video.fetcher import VideoFetcher
            return VideoFetcher()
        raise NotImplementedError(f"Tier '{self.tier}' video fetcher not implemented.")

    def _get_assembler(self):
        from src.video.assembler import VideoAssembler
        return VideoAssembler()

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(
        self,
        topic: str,
        voice: str | None = None,
        skip_research: Path | None = None,
        skip_script: Path | None = None,
    ) -> Path:
        """
        Run the full pipeline for a given topic.

        Args:
            topic:         Research topic string.
            voice:         edge-tts voice name override (e.g. "en-US-ChristopherNeural").
            skip_research: Path to an existing run folder or sources.json to skip Step 1.
            skip_script:   Path to an existing run folder or script.json to skip Step 2.

        Returns:
            Path to the rendered final.mp4.
        """
        import json

        slug = run_slug(topic)
        Config.set_run(slug)
        run_dir = Config.run_dir()

        console.print(f"\n[bold green]🎬 NotebookLM Auto Pipeline[/bold green]")
        console.print(f"[dim]Topic:[/dim]   [bold]{topic}[/bold]")
        console.print(f"[dim]Tier:[/dim]    [bold]{self.tier.upper()}[/bold]  (free)")
        console.print(f"[dim]Run ID:[/dim]  {slug}")
        console.print(f"[dim]Folder:[/dim]  {run_dir}\n")

        # ── Step 1: Research ──────────────────────────────────────────────────
        if skip_research:
            skip_research = Path(skip_research)
            sources_file = (
                skip_research / "research" / "sources.json"
                if skip_research.is_dir()
                else skip_research
            )
            console.print(f"[yellow]⏭  Skipping research → {sources_file}[/yellow]")
            research_data = json.loads(sources_file.read_text())
            # Backfill full_report from report.md if missing (e.g. loaded from sources.json)
            if "full_report" not in research_data:
                report_md = sources_file.parent / "report.md"
                if report_md.exists():
                    research_data["full_report"] = report_md.read_text(encoding="utf-8")
                else:
                    # Fallback: build a minimal report from sources content
                    research_data["full_report"] = "\n\n".join(
                        s.get("content", s.get("snippet", "")) for s in research_data.get("sources", [])
                    )
        else:
            with _make_progress() as progress:
                task = progress.add_task("🔍 Researching topic...", total=None)

                def research_cb(msg, _s, _t):
                    progress.update(task, description=f"🔍 {msg}")

                researcher = self._get_researcher()
                research_data = researcher.research(topic, progress_callback=research_cb)
                md_path = researcher.save(research_data, slug)
                progress.update(
                    task,
                    description=f"✅ Research complete — {len(research_data['sources'])} sources",
                )

            print_sources_table(research_data["sources"])
            console.print(f"[dim]Research saved → {md_path}[/dim]\n")

        # ── Step 2: Script Writing ────────────────────────────────────────────
        if skip_script:
            skip_script = Path(skip_script)
            script_file = (
                skip_script / "scripts" / "script.json"
                if skip_script.is_dir()
                else skip_script
            )
            console.print(f"[yellow]⏭  Skipping script writing → {script_file}[/yellow]")
            script = json.loads(script_file.read_text())
        else:
            with _make_progress() as progress:
                task = progress.add_task("✍️  Writing video script...", total=None)

                def script_cb(msg, _s, _t):
                    progress.update(task, description=f"✍️  {msg}")

                writer = self._get_script_writer()
                script = writer.write(research_data, progress_callback=script_cb)
                script_path = writer.save(script, slug)
                progress.update(
                    task,
                    description=f"✅ Script written — {len(script['scenes'])} scenes",
                )

            console.print(f"[bold white]📝 {script.get('title', '')}[/bold white]")
            console.print(f"[dim]Script saved → {script_path}[/dim]\n")

        # ── Step 3: Narration ─────────────────────────────────────────────────
        with _make_progress() as progress:
            task = progress.add_task("🎙️  Generating narration...", total=None)

            def audio_cb(msg, _s, _t):
                progress.update(task, description=f"🎙️  {msg}")

            narrator = self._get_narrator(voice=voice)
            audio_results = narrator.narrate_script(script, slug, progress_callback=audio_cb)
            progress.update(
                task,
                description=f"✅ Narration done — {len(audio_results)} audio files",
            )
        console.print()

        # ── Step 4: Fetch Stock Video ─────────────────────────────────────────
        with _make_progress() as progress:
            task = progress.add_task("🎞️  Fetching stock video clips...", total=None)

            def video_cb(msg, _s, _t):
                progress.update(task, description=f"🎞️  {msg}")

            fetcher = self._get_video_fetcher()
            video_results = fetcher.fetch_for_script(script, slug, progress_callback=video_cb)
            success = sum(1 for r in video_results if r.get("video_path"))
            progress.update(
                task,
                description=f"✅ Fetched {success}/{len(video_results)} clips",
            )
        console.print()

        # ── Step 5: Assemble Final Video ──────────────────────────────────────
        with _make_progress() as progress:
            task = progress.add_task("🎬 Assembling final video...", total=None)

            def assemble_cb(msg, _s, _t):
                progress.update(task, description=f"🎬 {msg}")

            assembler = self._get_assembler()
            final_path = assembler.assemble(
                script=script,
                audio_results=audio_results,
                video_results=video_results,
                slug=slug,
                progress_callback=assemble_cb,
            )
            progress.update(task, description="✅ Video rendered!")

        console.print(f"\n[bold green]🎉 Done![/bold green]")
        console.print(f"[bold white]   {final_path}[/bold white]")
        console.print(f"[dim]   All assets saved in: {run_dir}[/dim]\n")

        return final_path
