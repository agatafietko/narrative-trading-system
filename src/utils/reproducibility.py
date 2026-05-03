"""Reproducibility utilities.

Manages random seeds, data hashing, and logging for full reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime

import numpy as np

DEFAULT_SEED = 42


def set_global_seed(seed: int = DEFAULT_SEED) -> None:
    """Set all random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)


def hash_content(content: str) -> str:
    """SHA-256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_prompt(prompt: str) -> str:
    """Hash a prompt for logging/reproducibility."""
    return hash_content(prompt)


def hash_data_record(source: str, title: str, date: str) -> str:
    """Deduplication hash for articles and similar records."""
    return hash_content(f"{title}|{source}|{date}")


def generate_run_id() -> str:
    """Generate a unique run ID for a backtest or live run."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    rand = hashlib.md5(str(random.random()).encode()).hexdigest()[:6]
    return f"run_{ts}_{rand}"


def log_llm_call(
    agent_name: str,
    model: str,
    prompt: str,
    response: str,
    latency_ms: int,
) -> dict:
    """Create a reproducibility log entry for an LLM call."""
    return {
        "agent_name": agent_name,
        "model": model,
        "prompt_hash": hash_prompt(prompt),
        "response_hash": hash_content(response),
        "prompt_length": len(prompt),
        "response_length": len(response),
        "latency_ms": latency_ms,
        "timestamp": datetime.utcnow().isoformat(),
    }
