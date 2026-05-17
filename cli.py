#!/usr/bin/env python3
"""
NotebookLM Auto — CLI Entry Point

Usage examples:
  python cli.py --topic "US Housing Market"
  python cli.py --topic "Climate Change" --tier a --voice en-US-ChristopherNeural
  python cli.py --topic "AI in Healthcare" --duration 180
  python cli.py --list-voices
"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import Config

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """NotebookLM Auto — Research any topic and generate a cinematic educational video."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option(
    "--topic", "-t",
    required=True,
    help='Topic to research and create a video about. e.g. "US Housing Market"',
)
@click.option(
    "--tier", "-T",
    default=None,
    type=click.Choice(["a", "b", "c"], case_sensitive=False),
    help="Pipeline tier: a=free (default), b=low-cost, c=premium-Gemini",
)
@click.option(
    "--voice", "-v",
    default=None,
    help="TTS voice name (edge-tts). Default: en-US-GuyNeural. Use --list-voices to see options.",
)
@click.option(
    "--duration", "-d",
    default=None,
    type=int,
    help="Target video duration in seconds (default: 240 = 4 min). Range: 180–300.",
)
@click.option(
    "--skip-research",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Skip research step — provide path to an existing research JSON file.",
)
@click.option(
    "--skip-script",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Skip script-writing step — provide path to an existing script JSON file.",
)
def run(topic, tier, voice, duration, skip_research, skip_script):
    """Run the full research-to-video pipeline for a topic."""

    # Apply overrides
    if tier:
        Config.DEFAULT_TIER = tier
    if duration:
        Config.TARGET_DURATION_SECONDS = max(60, min(600, duration))
    effective_tier = tier or Config.DEFAULT_TIER

    # Validate API keys
    missing = Config.validate(effective_tier)
    if missing:
        console.print(
            Panel(
                f"[red]Missing API keys in .env:[/red]\n" +
                "\n".join(f"  • {k}" for k in missing) +
                "\n\nSee [bold].env.example[/bold] for setup instructions.",
                title="❌ Configuration Error",
                border_style="red",
            )
        )
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]Topic:[/bold cyan] {topic}\n"
            f"[bold cyan]Tier:[/bold cyan]  {effective_tier.upper()} ({'Free' if effective_tier == 'a' else 'Paid'})\n"
            f"[bold cyan]Voice:[/bold cyan] {voice or Config.DEFAULT_VOICE}\n"
            f"[bold cyan]Duration:[/bold cyan] ~{Config.TARGET_DURATION_SECONDS // 60} min",
            title="🎬 NotebookLM Auto",
            border_style="cyan",
        )
    )

    from src.pipeline import Pipeline
    pipeline = Pipeline(tier=effective_tier)

    try:
        output_path = pipeline.run(
            topic=topic,
            voice=voice,
            skip_research=skip_research,
            skip_script=skip_script,
        )
        console.print(
            Panel(
                f"[green]Video created successfully![/green]\n\n"
                f"[bold white]{output_path}[/bold white]\n\n"
                f"Open with: [dim]open {output_path}[/dim]",
                title="✅ Complete",
                border_style="green",
            )
        )
        # Auto-open on macOS
        import subprocess
        subprocess.run(["open", str(output_path)], check=False)

    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user.[/yellow]")
        sys.exit(0)
    except Exception as exc:
        console.print(
            Panel(
                f"[red]{type(exc).__name__}:[/red] {exc}\n\n"
                "[dim]Check outputs/ folder for any partially completed files.\n"
                "You can resume using --skip-research or --skip-script flags.[/dim]",
                title="❌ Pipeline Error",
                border_style="red",
            )
        )
        raise sys.exit(1)


@cli.command("list-voices")
def list_voices():
    """List available TTS voices (English only)."""
    console.print("[cyan]Loading available voices...[/cyan]")
    from src.audio.narrator import Narrator
    voices = Narrator.list_voices()

    table = Table(title="Available English TTS Voices (edge-tts)", show_lines=False)
    table.add_column("Voice Name", style="cyan", no_wrap=True)
    table.add_column("Gender", style="magenta")
    table.add_column("Locale", style="green")

    for v in sorted(voices, key=lambda x: x["ShortName"]):
        table.add_row(
            v["ShortName"],
            v.get("Gender", "?"),
            v.get("Locale", "?"),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(voices)} English voices[/dim]")
    console.print("[dim]Use with:[/dim] [bold]python cli.py run --topic '...' --voice en-US-GuyNeural[/bold]")


@cli.command()
def check():
    """Check configuration and API key status."""
    table = Table(title="Configuration Status", show_lines=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value / Status", style="white")

    checks = [
        ("Tier A: TAVILY_API_KEY", Config.TAVILY_API_KEY, "tavily"),
        ("Tier A: GROQ_API_KEY", Config.GROQ_API_KEY, "groq"),
        ("Tier A: PEXELS_API_KEY", Config.PEXELS_API_KEY, "pexels"),
        ("Default Voice", Config.DEFAULT_VOICE, None),
        ("Target Duration", f"{Config.TARGET_DURATION_SECONDS}s (~{Config.TARGET_DURATION_SECONDS//60} min)", None),
        ("Video Resolution", f"{Config.VIDEO_WIDTH}×{Config.VIDEO_HEIGHT}", None),
        ("Output Directory", str(Config.OUTPUT_DIR), None),
    ]

    for label, value, key_type in checks:
        if key_type:
            if not value or "your-key" in value.lower() or "regenerate" in value.lower():
                status = "[red]❌ NOT SET[/red]"
            else:
                masked = value[:8] + "..." + value[-4:]
                status = f"[green]✅ Set[/green] ({masked})"
        else:
            status = str(value)
        table.add_row(label, status)

    console.print(table)


if __name__ == "__main__":
    cli()
