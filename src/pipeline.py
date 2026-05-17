"""
Pipeline orchestrator — coordinates all stages of the research-to-video pipeline.
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

    Tier A (default): Tavily + Groq + edge-tts + Pexels + MoviePy  (~$0)
    Tier B (future):  Perplexity + ElevenLabs + FLUX images + Pexels (~$2)
    Tier C (future):  Gemini Deep Research + Gemini TTS + Veo 3.1   (~$20)
    """

    def __init__(self, tier: str = "a") -> None:
        self.tier = tier.lower()

    def _get_researcher(self):
        if self.tier == "a":
            from src.research.deep_research import DeepResearcher
            return DeepResearcher()
        raise NotImplementedError(f"Tier {self.tier} researcher not yet implemented.")

    def _get_script_writer(self):
        if self.tier in ("a", "b"):
            from src.script.script_writer import ScriptWriter
            return ScriptWriter()
        raise NotImplementedError(f"Tier {self.tier} script writer not yet implemented.")

    def _get_narrator(self, voice: str | None = None):
        from src.audio.narrator import Narrator
        return Narrator(voice=voice)

    def _get_video_fetcher(self):
        if self.tier == "a":
            from src.video.fetcher import VideoFetcher
            return VideoFetcher()
        raise NotImplementedError(f"Tier {self.tier} video fetcher not yet implemented.")

    def _get_assembler(self):
        from src.video.assembler import VideoAssembler
        return VideoAssembler()

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
            topic: Research topic (e.g. "US Housing Market")
            voice: edge-tts voice name override
            skip_research: Path to existing research .json to skip research step
            skip_script: Path to existing script .json to skip script step

        Returns:
            Path to the final output video
        """
        import json

        slug = run_slug(topic)

        # ── Set up per-run project folder ─────────────────────────────────────
        Config.set_run(slug)
        run_dir = Config.run_dir()

        console.print(f"\n[bold green]🎬 NotebookLM Auto Pipeline[/bold green]")
        console.print(f"[dim]Topic:[/dim]   [bold]{topic}[/bold]")
        console.print(f"[dim]Tier:[/dim]    [bold]{self.tier.upper()}[/bold]")
        console.print(f"[dim]Run ID:[/dim]  {slug}")
        console.print(f"[dim]Folder:[/dim]  {run_dir}\n")

        # ── Step 1: Research ──────────────────────────────────────────────────
        if skip_research:
            # Accept either a run folder or direct path to sources.json
            skip_research = Path(skip_research)
            sources_file = (
                skip_research / "research" / "sources.json"
                if skip_research.is_dir()
                else skip_research
            )
            console.print(f"[yellow]⏭  Skipping research (using: {sources_file})[/yellow]")
            research_data = json.loads(sources_file.read_text())
        else:
            with _make_progress() as progress:
                task = progress.add_task("🔍 Researching topic...", total=None)

                def research_cb(msg, step, total):
                    progress.update(task, description=f"🔍 {msg}")

                researcher = self._get_researcher()
                research_data = researcher.research(topic, progress_callback=research_cb)
                md_path = researcher.save(research_data, slug)
                progress.update(task, description=f"✅ Research complete — {len(research_data['sources'])} sources")

            print_sources_table(research_data["sources"])
            console.print(f"[dim]Research saved to:[/dim] {md_path}\n")

        # ── Step 2: Script Writing ────────────────────────────────────────────
        if skip_script:
            # Accept either a run folder or direct path to script.json
            skip_script = Path(skip_script)
            script_file = (
                skip_script / "scripts" / "script.json"
                if skip_script.is_dir()
                else skip_script
            )
            console.print(f"[yellow]⏭  Skipping script writing (using: {script_file})[/yellow]")
            script = json.loads(script_file.read_text())
        else:
            with _make_progress() as progress:
                task = progress.add_task("✍️  Writing video script...", total=None)

                def script_cb(msg, step, total):
                    progress.update(task, description=f"✍️  {msg}")

                writer = self._get_script_writer()
                script = writer.write(research_data, progress_callback=script_cb)
                script_path = writer.save(script, slug)
                progress.update(task, description=f"✅ Script written — {len(script['scenes'])} scenes")

            console.print(f"[bold white]📝 Video Title:[/bold white] {script.get('title', '')}")
            console.print(f"[dim]Script saved to:[/dim] {script_path}\n")

        # ── Step 3: Narration ─────────────────────────────────────────────────
        with _make_progress() as progress:
            task = progress.add_task("🎙️  Generating narration...", total=None)

            def audio_cb(msg, step, total):
                progress.update(task, description=f"🎙️  {msg}")

            narrator = self._get_narrator(voice=voice)
            audio_results = narrator.narrate_script(script, slug, progress_callback=audio_cb)
            progress.update(task, description=f"✅ Narration done — {len(audio_results)} audio files")

        console.print()

        # ── Step 4: Fetch Stock Video ─────────────────────────────────────────
        with _make_progress() as progress:
            task = progress.add_task("🎞️  Fetching stock video clips...", total=None)

            def video_cb(msg, step, total):
                progress.update(task, description=f"🎞️  {msg}")

            fetcher = self._get_video_fetcher()
            video_results = fetcher.fetch_for_script(script, slug, progress_callback=video_cb)

            success = sum(1 for r in video_results if r.get("video_path"))
            progress.update(task, description=f"✅ Fetched {success}/{len(video_results)} clips")

        console.print()

        # ── Step 5: Assemble Final Video ─────────────────────────────────────
        with _make_progress() as progress:
            task = progress.add_task("🎬 Assembling final video...", total=None)

            def assemble_cb(msg, step, total):
                progress.update(task, description=f"🎬 {msg}")

            assembler = self._get_assembler()
            final_path = assembler.assemble(
                script=script,
                audio_results=audio_results,
                video_results=video_results,
                slug=slug,
                progress_callback=assemble_cb,
            )
            progress.update(task, description=f"✅ Video rendered!")

        console.print(f"\n[bold green]🎉 Done! Your video is ready:[/bold green]")
        console.print(f"[bold white]   {final_path}[/bold white]")
        console.print(f"[dim]   All assets saved in: {run_dir}[/dim]\n")

        return final_path
