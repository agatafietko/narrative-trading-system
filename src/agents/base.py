"""BaseAgent — multi-model LLM agent base class.

Provides a unified interface for calling different LLM providers
(OpenAI, Anthropic, Google, Together/open-source) with structured
output parsing, logging, and reproducibility tracking.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from src.utils.logging import get_logger
from src.utils.reproducibility import hash_prompt, hash_content

logger = get_logger("agent.base")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"


def load_model_config(agent_path: str) -> dict:
    """Load model config for a specific agent.

    Args:
        agent_path: Dot-separated path like 'gatherers.macro_sentinel'
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    parts = agent_path.split(".")
    result = config
    for part in parts:
        result = result[part]
    return result


class BaseAgent:
    """Base class for LLM-powered agents.

    Handles model initialization, prompt formatting, LLM calls,
    structured output parsing, and call logging.
    """

    def __init__(self, agent_name: str, config_path: str):
        """
        Args:
            agent_name: Human-readable agent name.
            config_path: Path in models.yaml (e.g., 'gatherers.macro_sentinel').
        """
        self.agent_name = agent_name
        self.config = load_model_config(config_path)
        self.provider = self.config["provider"]
        self.model_name = self.config["model"]
        self.temperature = self.config.get("temperature", 0)
        self.max_tokens = self.config.get("max_tokens", 2000)

        self._client = None
        logger.info(f"Initialized {agent_name} with {self.provider}/{self.model_name}")

    def _get_client(self):
        """Lazy-initialize the LLM client."""
        if self._client is not None:
            return self._client

        if self.provider == "openai":
            from langchain_openai import ChatOpenAI
            self._client = ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        elif self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            self._client = ChatAnthropic(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        elif self.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            self._client = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
        elif self.provider == "together":
            from langchain_openai import ChatOpenAI
            import os
            self._client = ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                openai_api_key=os.getenv("TOGETHER_API_KEY"),
                openai_api_base="https://api.together.xyz/v1",
            )
        elif self.provider == "deepseek":
            from langchain_openai import ChatOpenAI
            import os
            self._client = ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
                openai_api_base="https://api.deepseek.com",
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        return self._client

    def call_llm(self, prompt: str, system_prompt: str = "") -> dict:
        """Call the LLM and return the response with metadata.

        Args:
            prompt: The user/main prompt.
            system_prompt: Optional system prompt.

        Returns:
            Dict with 'content', 'prompt_hash', 'response_hash', 'latency_ms',
            'model_used'.
        """
        client = self._get_client()

        messages = []
        if system_prompt:
            messages.append(("system", system_prompt))
        messages.append(("human", prompt))

        start = time.time()
        response = client.invoke(messages)
        latency_ms = int((time.time() - start) * 1000)

        content = response.content if hasattr(response, "content") else str(response)

        result = {
            "content": content,
            "prompt_hash": hash_prompt(prompt),
            "response_hash": hash_content(content),
            "latency_ms": latency_ms,
            "model_used": f"{self.provider}/{self.model_name}",
        }

        logger.info(
            f"{self.agent_name} LLM call: {latency_ms}ms, "
            f"response length: {len(content)} chars"
        )

        return result

    def parse_json_response(self, content: str) -> dict | list:
        """Extract and parse JSON from an LLM response.

        Handles responses that include markdown code fences.
        """
        # Strip markdown code fences
        text = content.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object/array in the response
            for start_char, end_char in [("{", "}"), ("[", "]")]:
                start_idx = text.find(start_char)
                end_idx = text.rfind(end_char)
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    try:
                        return json.loads(text[start_idx:end_idx + 1])
                    except json.JSONDecodeError:
                        continue

            logger.error(f"Failed to parse JSON from {self.agent_name}: {text[:200]}")
            return {}
