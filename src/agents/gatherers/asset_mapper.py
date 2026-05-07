"""Asset Mapper — translates multi-modal signals to per-ticker directional views.

Sits between signal_aggregator and strategist. Uses Claude Sonnet to produce
a directional score (-1.0 to +1.0) for each instrument in the trading universe.
"""

from __future__ import annotations

from datetime import datetime

from src.agents.base import BaseAgent
from src.utils.logging import get_logger

logger = get_logger("agent.asset_mapper")

SYSTEM_PROMPT = (
    "You are an asset mapping specialist. You translate macro, narrative, sentiment, "
    "and technical signals into explicit per-instrument directional views. "
    "Be concise and specific. Return only valid JSON."
)


class AssetMapper(BaseAgent):
    """Translates gathered signals into per-ticker directional scores."""

    INSTRUMENTS = [
        "SPY", "QQQ", "IWM", "EEM", "TLT", "SHY",
        "GLD", "USO", "UUP", "VIXY", "BTC-USD",
    ]

    def __init__(self):
        super().__init__("asset_mapper", "gatherers.asset_mapper")

    def map_assets(self, signals: list[dict], as_of: datetime) -> dict:
        """Consume all gatherer signals, call Claude, return signal payload dict.

        Returns empty views dict on failure (graceful degradation).
        """
        context = self._build_context(signals)
        prompt = self._build_prompt(context)

        try:
            response = self.call_llm(prompt, system_prompt=SYSTEM_PROMPT)
            parsed = self.parse_json_response(response["content"])
        except Exception as e:
            logger.warning(f"[AssetMapper] LLM call failed: {e}")
            return {
                "views": {}, "rationale": {}, "dominant_theme": "",
                "confidence": 0.0, "model_used": f"{self.provider}/{self.model_name}",
                "prompt_hash": "", "response_hash": "", "latency_ms": 0,
            }

        if not parsed or not isinstance(parsed, dict):
            return {
                "views": {}, "rationale": {}, "dominant_theme": "",
                "confidence": 0.0, "model_used": response["model_used"],
                "prompt_hash": response["prompt_hash"],
                "response_hash": response["response_hash"],
                "latency_ms": response["latency_ms"],
            }

        # Clamp all scores to [-1.0, 1.0]; fill missing tickers with 0.0
        raw_views = parsed.get("views", {})
        views = {}
        for ticker in self.INSTRUMENTS:
            try:
                score = float(raw_views.get(ticker, 0.0))
            except (TypeError, ValueError):
                score = 0.0
            views[ticker] = max(-1.0, min(1.0, score))

        return {
            "views": views,
            "rationale": parsed.get("rationale", {}),
            "dominant_theme": parsed.get("dominant_theme", ""),
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            "model_used": response["model_used"],
            "prompt_hash": response["prompt_hash"],
            "response_hash": response["response_hash"],
            "latency_ms": response["latency_ms"],
        }

    def _build_context(self, signals: list[dict]) -> str:
        """Extract relevant fields from each signal type into a readable context block."""
        signal_map: dict[str, dict] = {}
        for s in signals:
            signal_map[s.get("signal_type", "unknown")] = s.get("payload", {})

        macro = signal_map.get("macro", {})
        narrative = signal_map.get("narrative", {})
        sentiment = signal_map.get("sentiment", {})
        technical = signal_map.get("technical", {})

        lines = []

        # Macro
        regime = macro.get("regime", "unknown")
        regime_conf = macro.get("regime_confidence", 0.0)
        macro_summary = macro.get("macro_summary", "No macro data.")
        lines.append(f"MACRO REGIME: {regime}, confidence {regime_conf:.0%}")
        lines.append(f"MACRO SUMMARY: {macro_summary}")
        lines.append("")

        # Narrative
        dom_narratives = narrative.get("dominant_narratives", [])
        news_sentiment = narrative.get("overall_news_sentiment", "neutral")
        # dominant_narratives may be strings or dicts — normalise to strings
        dom_strs = [
            n if isinstance(n, str) else n.get("name", str(n))
            for n in dom_narratives
        ]
        lines.append(f"DOMINANT NARRATIVES: {', '.join(dom_strs) if dom_strs else 'none'}")
        lines.append(f"NEWS SENTIMENT: {news_sentiment}")
        lines.append("")

        # Sentiment
        fear_greed = sentiment.get("fear_greed_score", "N/A")
        crowd_sentiment = sentiment.get("overall_crowd_sentiment", "neutral")
        lines.append(f"CROWD SENTIMENT: fear_greed={fear_greed}/100, overall={crowd_sentiment}")
        lines.append("")

        # Technical
        momentum_summary = technical.get("momentum_summary", "No technical data.")
        indicators = technical.get("indicators", {})
        lines.append("TECHNICAL SIGNALS:")
        lines.append(f"  Momentum: {momentum_summary}")
        for ticker, ind in indicators.items():
            rsi = ind.get("rsi", "N/A")
            lines.append(f"  {ticker}: RSI={rsi}")

        return "\n".join(lines)

    def _build_prompt(self, context: str) -> str:
        """Assemble the final user prompt."""
        instruments_str = ", ".join(self.INSTRUMENTS)
        return (
            f"{context}\n\n"
            f"INSTRUMENTS: {instruments_str}\n\n"
            "For each instrument produce a directional score from -1.0 (strong underweight) "
            "to +1.0 (strong overweight) and a one-sentence rationale. "
            "Also produce an overall confidence score (0.0–1.0) and a dominant_theme string.\n\n"
            "Return only valid JSON in this exact format:\n"
            "{\n"
            '  "views": {"SPY": <float>, ...},\n'
            '  "rationale": {"SPY": "<one sentence>", ...},\n'
            '  "dominant_theme": "<string>",\n'
            '  "confidence": <float>\n'
            "}"
        )
