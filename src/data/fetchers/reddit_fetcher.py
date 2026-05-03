"""Reddit data fetcher.

Fetches posts from finance-related subreddits for sentiment analysis.
Uses PRAW (Python Reddit API Wrapper).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import yaml

from src.state.store import DataStore
from src.utils.logging import get_logger

logger = get_logger("fetcher.reddit")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "data_sources.yaml"


def load_reddit_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["reddit"]


def fetch_reddit_posts(
    client_id: str,
    client_secret: str,
    user_agent: str = "narrative-trading-system/0.1",
) -> list[dict]:
    """Fetch posts from configured subreddits.

    Args:
        client_id: Reddit API client ID.
        client_secret: Reddit API client secret.
        user_agent: Reddit API user agent string.

    Returns:
        List of post records ready for storage.
    """
    import praw

    config = load_reddit_config()
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    records = []
    for subreddit_name in config["subreddits"]:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            sort = config.get("sort", "hot")
            limit = config.get("posts_per_subreddit", 50)

            if sort == "hot":
                posts = subreddit.hot(limit=limit)
            elif sort == "top":
                posts = subreddit.top(time_filter="day", limit=limit)
            else:
                posts = subreddit.new(limit=limit)

            for post in posts:
                created_utc = datetime.utcfromtimestamp(post.created_utc).isoformat()
                records.append({
                    "post_id": post.id,
                    "subreddit": subreddit_name,
                    "title": post.title,
                    "body": (post.selftext or "")[:2000],
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "created_utc": created_utc,
                    "known_at": created_utc,  # Posts are known at creation time
                })

            logger.info(f"r/{subreddit_name}: fetched {limit} posts")

        except Exception as e:
            logger.warning(f"Reddit error for r/{subreddit_name}: {e}")
            continue

    logger.info(f"Reddit: fetched {len(records)} total posts")
    return records


def fetch_and_store(
    store: DataStore,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> int:
    """Fetch Reddit posts and store in database."""
    if not client_id:
        client_id = os.getenv("REDDIT_CLIENT_ID")
    if not client_secret:
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning("Reddit credentials not set — skipping")
        return 0

    user_agent = os.getenv("REDDIT_USER_AGENT", "narrative-trading-system/0.1")
    records = fetch_reddit_posts(client_id, client_secret, user_agent)

    if not records:
        return 0

    inserted = store.insert_reddit_posts(records)
    logger.info(f"Stored {inserted} Reddit posts")
    return inserted
