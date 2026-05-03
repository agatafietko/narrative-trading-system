"""Sentiment Scout — social media and crowd sentiment agent.

Uses Gemini Flash for cost-effective high-volume social media processing.
Analyzes Reddit posts and GDELT tone data for fear/greed signals and
extreme positioning.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.agents.base import BaseAgent
from src.state.schema import Signal
from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("agent.sentiment_scout")

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "sentiment_scout.txt"


class SentimentScout(BaseAgent):
    """Analyzes crowd sentiment from Reddit and GDELT data."""

    def __init__(self):
        super().__init__("sentiment_scout", "gatherers.sentiment_scout")
        self.prompt_template = PROMPT_PATH.read_text()

    def generate_signal(self, store: DataStore, as_of: datetime) -> Signal:
        """Generate a sentiment signal from social media data.

        Args:
            store: DataStore for point-in-time data access.
            as_of: Current simulation timestamp.

        Returns:
            Signal with sentiment analysis payload.
        """
        reddit_posts = store.get_reddit_posts_as_of(as_of, lookback_days=3)
        gdelt_data = store.get_gdelt_data_as_of(as_of, lookback_days=7)

        reddit_text = self._format_reddit(reddit_posts)
        gdelt_text = self._format_gdelt(gdelt_data)

        prompt = self.prompt_template.format(
            as_of=as_of.strftime("%Y-%m-%d"),
            reddit_data=reddit_text,
            gdelt_tone=gdelt_text,
        )

        response = self.call_llm(prompt)
        payload = self.parse_json_response(response["content"])

        if not payload:
            logger.warning("Failed to parse sentiment signal")
            payload = {
                "overall_crowd_sentiment": "neutral",
                "fear_greed_score": 50,
                "confidence": 0.3,
            }

        return Signal(
            agent_name="sentiment_scout",
            signal_type="sentiment",
            as_of=as_of,
            confidence=payload.get("confidence", 0.5),
            payload={
                **payload,
                "model_used": response["model_used"],
                "prompt_hash": response["prompt_hash"],
                "response_hash": response["response_hash"],
                "latency_ms": response["latency_ms"],
                "posts_analyzed": len(reddit_posts),
            },
        )

    def _format_reddit(self, posts: list[dict], max_posts: int = 30) -> str:
        """Format Reddit posts for the prompt."""
        if not posts:
            return "No recent Reddit posts available."

        lines = []
        for i, post in enumerate(posts[:max_posts]):
            sub = post.get("subreddit", "unknown")
            title = post.get("title", "")
            score = post.get("score", 0)
            comments = post.get("num_comments", 0)
            body = post.get("body", "")

            if body and len(body) > 200:
                body = body[:200] + "..."

            lines.append(
                f"[{i+1}] r/{sub} | Score: {score} | Comments: {comments}\n"
                f"    Title: {title}\n"
                f"    Body: {body}" if body else
                f"[{i+1}] r/{sub} | Score: {score} | Comments: {comments}\n"
                f"    Title: {title}"
            )

        return "\n\n".join(lines)

    def _format_gdelt(self, gdelt_data) -> str:
        """Format GDELT tone data for the prompt."""
        if gdelt_data is None or (hasattr(gdelt_data, "empty") and gdelt_data.empty):
            return "No GDELT tone data available."

        lines = []
        if hasattr(gdelt_data, "iterrows"):
            for _, row in gdelt_data.iterrows():
                lines.append(
                    f"- {row.get('date', 'N/A')}: theme={row.get('themes', 'N/A')}, "
                    f"tone={row.get('tone', 0):.2f}"
                )
        return "\n".join(lines) if lines else "No GDELT tone data available."
