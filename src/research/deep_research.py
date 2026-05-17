"""
Deep web research using Tavily Search API (Tier A).

Performs multi-query search on a topic, fetches full content from top URLs,
and assembles a structured research report with cited sources.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import Config


# ── Research queries strategy ─────────────────────────────────────────────────

def _build_queries(topic: str) -> list[str]:
    """Generate diverse sub-queries to cover the topic comprehensively."""
    return [
        f"{topic} overview and current state 2025 2026",
        f"{topic} key statistics data trends",
        f"{topic} causes factors driving forces",
        f"{topic} future outlook forecast predictions",
        f"{topic} impact on everyday people beginners guide",
    ]


# ── Tavily search ─────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _tavily_search(client: TavilyClient, query: str, max_results: int = 5) -> list[dict]:
    """Run a single Tavily search query and return results."""
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content=True,
        include_answer=True,
    )
    return response.get("results", [])


# ── Content cleaning ──────────────────────────────────────────────────────────

def _clean_content(raw: str | None, max_chars: int = 3000) -> str:
    """Strip HTML tags and truncate content."""
    if not raw:
        return ""
    # Remove HTML if present
    if "<" in raw and ">" in raw:
        soup = BeautifulSoup(raw, "lxml")
        text = soup.get_text(separator=" ", strip=True)
    else:
        text = raw
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ── Main researcher class ─────────────────────────────────────────────────────

class DeepResearcher:
    """Tier A researcher using Tavily API."""

    def __init__(self) -> None:
        self.client = TavilyClient(api_key=Config.TAVILY_API_KEY)

    def research(self, topic: str, progress_callback=None) -> dict:
        """
        Run full research on a topic.

        Returns a dict with:
          - topic: str
          - timestamp: str
          - sources: list of {title, url, content, score}
          - summary_blocks: list of str (per-query answers)
          - full_report: str (assembled markdown report)
        """
        queries = _build_queries(topic)
        all_results: list[dict] = []
        seen_urls: set[str] = set()
        summary_blocks: list[str] = []

        for i, query in enumerate(queries):
            if progress_callback:
                progress_callback(f"Searching: {query}", i + 1, len(queries))

            results = _tavily_search(self.client, query, max_results=5)

            for r in results:
                url = r.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                content = _clean_content(
                    r.get("raw_content") or r.get("content", "")
                )
                if not content:
                    continue

                all_results.append(
                    {
                        "title": r.get("title", "Untitled"),
                        "url": url,
                        "content": content,
                        "score": r.get("score", 0.0),
                        "query": query,
                    }
                )

            # Capture Tavily's synthesized answer per query
            # (re-issue a quick context call for the answer)
            try:
                answer_resp = self.client.search(
                    query=query,
                    search_depth="basic",
                    max_results=3,
                    include_answer=True,
                )
                answer = answer_resp.get("answer", "")
                if answer:
                    summary_blocks.append(f"**{query}**\n{answer}")
            except Exception:
                pass

        # Sort by relevance score
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top_sources = all_results[:12]  # Keep top 12 sources

        full_report = _build_report(topic, top_sources, summary_blocks)

        return {
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "sources": top_sources,
            "summary_blocks": summary_blocks,
            "full_report": full_report,
        }

    def save(self, research_data: dict, slug: str) -> Path:
        """Save research to disk as .md and .json files."""
        Config.ensure_dirs()
        base = Config.research_dir() / "report"

        # Save markdown report
        md_path = base.with_suffix(".md")
        md_path.write_text(research_data["full_report"], encoding="utf-8")

        # Save structured JSON (sources + metadata)
        json_path = Config.research_dir() / "sources.json"
        json_data = {
            "topic": research_data["topic"],
            "timestamp": research_data["timestamp"],
            "sources": [
                {"title": s["title"], "url": s["url"], "score": s["score"]}
                for s in research_data["sources"]
            ],
        }
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

        return md_path


def _build_report(topic: str, sources: list[dict], summary_blocks: list[str]) -> str:
    """Assemble a readable markdown research report."""
    lines = [
        f"# Research Report: {topic}",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n",
        "---\n",
        "## Key Findings\n",
    ]

    for block in summary_blocks:
        lines.append(block)
        lines.append("")

    lines += [
        "\n---\n",
        "## Source Details\n",
    ]

    for i, src in enumerate(sources, 1):
        lines.append(f"### Source {i}: [{src['title']}]({src['url']})")
        lines.append(f"*Relevance score: {src['score']:.2f}*\n")
        lines.append(src["content"])
        lines.append("\n---\n")

    lines += [
        "## Sources List\n",
    ]
    for i, src in enumerate(sources, 1):
        lines.append(f"{i}. [{src['title']}]({src['url']})")

    return "\n".join(lines)
