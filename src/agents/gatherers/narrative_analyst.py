"""Narrative Analyst — news and event interpretation agent.

Uses Claude Sonnet for strong long-context reasoning across many articles.
Extracts tradable narratives from news flow and GDELT event data.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.agents.base import BaseAgent
from src.state.schema import Signal
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.narrative_analyst")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "narrative_analyst.txt"


class NarrativeAnalyst(BaseAgent):
    """Extracts tradable narratives from news articles and GDELT data."""

    def __init__(self):
        super().__init__("narrative_analyst", "gatherers.narrative_analyst")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_signal(self, store: DataStore, as_of: datetime) -> Signal:
        """Generate a narrative signal from news and GDELT data.

        Args:
            store: DataStore for point-in-time data access.
            as_of: Current simulation timestamp.

        Returns:
            Signal with narrative analysis payload.
        """
        # Fetch articles available as of this date
        articles = store.get_articles_as_of(as_of, lookback_days=7)
        gdelt_data = store.get_gdelt_data_as_of(as_of, lookback_days=7)

        # Format for prompt
        articles_text = self._format_articles(articles)
        gdelt_text = self._format_gdelt(gdelt_data)

        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            articles=articles_text,
            gdelt_data=gdelt_text,
        )

        response = self.call_llm(prompt)
        payload = self.parse_json_response(response["content"])

        if not payload:
            logger.warning("Failed to parse narrative signal")
            payload = {
                "dominant_narratives": [],
                "overall_news_sentiment": "mixed",
                "confidence": 0.3,
            }

        return Signal(
            agent_name="narrative_analyst",
            signal_type="narrative",
            as_of=as_of,
            confidence=payload.get("confidence", 0.5),
            payload={
                **payload,
                "model_used": response["model_used"],
                "prompt_hash": response["prompt_hash"],
                "response_hash": response["response_hash"],
                "latency_ms": response["latency_ms"],
                "articles_analyzed": len(articles),
            },
        )

    def _format_articles(self, articles: list[dict], max_articles: int = 30) -> str:
        """Format articles for the prompt, respecting context limits."""
        if not articles:
            return "No recent articles available."

        lines = []
        for i, article in enumerate(articles[:max_articles]):
            source = article.get("source", "Unknown")
            title = article.get("title", "No title")
            published = article.get("published_at", "Unknown date")
            content = article.get("content", "")

            # Truncate content to keep prompt manageable
            if content and len(content) > 300:
                content = content[:300] + "..."

            lines.append(
                f"[{i+1}] {source} ({published[:10]})\n"
                f"    Title: {title}\n"
                f"    Content: {content}"
            )

        return "\n\n".join(lines)

    def _format_gdelt(self, gdelt_data) -> str:
        """Format GDELT data for the prompt."""
        if gdelt_data is None or (hasattr(gdelt_data, "empty") and gdelt_data.empty):
            return "No GDELT data available."

        lines = []
        if hasattr(gdelt_data, "iterrows"):
            for _, row in gdelt_data.iterrows():
                lines.append(
                    f"- {row.get('date', 'N/A')}: theme={row.get('themes', 'N/A')}, "
                    f"tone={row.get('tone', 0):.2f}, articles={row.get('num_articles', 0)}"
                )
        return "\n".join(lines) if lines else "No GDELT data available."
