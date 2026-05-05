"""Tests for Finnhub fetcher."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.data.fetchers.finnhub_fetcher import (
    fetch_company_news,
    fetch_market_news,
    fetch_and_store,
)


SAMPLE_ARTICLE = {
    "category": "company news",
    "datetime": 1735689600,  # 2026-01-01 00:00:00 UTC
    "headline": "SPY hits record high",
    "id": 123456,
    "image": "",
    "related": "SPY",
    "source": "Reuters",
    "summary": "SPY ETF reached a new all-time high on Wednesday.",
    "url": "https://reuters.com/spy-record",
}

SAMPLE_MARKET_ARTICLE = {
    "category": "general",
    "datetime": 1735689600,
    "headline": "Fed holds rates steady",
    "id": 789012,
    "image": "",
    "related": "",
    "source": "Bloomberg",
    "summary": "The Federal Reserve held interest rates steady at its January meeting.",
    "url": "https://bloomberg.com/fed-rates",
}


class TestFetchCompanyNews:
    def test_returns_list_of_records(self):
        """fetch_company_news returns a list of article dicts."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.return_value = [SAMPLE_ARTICLE]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert len(results) == 1
        assert results[0]["source"] == "Reuters"
        assert results[0]["title"] == "SPY hits record high"

    def test_record_has_required_fields(self):
        """Each record has all fields required by insert_articles."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.return_value = [SAMPLE_ARTICLE]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        record = results[0]
        for field in ("source", "title", "content", "url", "published_at", "known_at", "content_hash"):
            assert field in record, f"Missing field: {field}"

    def test_deduplicates_by_content_hash(self):
        """Duplicate articles (same source+title+date) are deduplicated."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.return_value = [SAMPLE_ARTICLE, SAMPLE_ARTICLE]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert len(results) == 1

    def test_skips_ticker_on_api_error(self):
        """A failing ticker is skipped; other tickers still processed."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.company_news.side_effect = [
                Exception("API error"),
                [SAMPLE_ARTICLE],
            ]

            results = fetch_company_news(
                api_key="test_key",
                tickers=["BAD", "SPY"],
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert len(results) == 1
        assert results[0]["title"] == "SPY hits record high"


class TestFetchMarketNews:
    def test_returns_list_of_records(self):
        """fetch_market_news returns a list of article dicts."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.general_news.return_value = [SAMPLE_MARKET_ARTICLE]

            results = fetch_market_news(api_key="test_key")

        assert len(results) >= 1
        assert results[0]["source"] == "Bloomberg"

    def test_record_has_required_fields(self):
        """Each market news record has all fields required by insert_articles."""
        with patch("src.data.fetchers.finnhub_fetcher.finnhub.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.general_news.return_value = [SAMPLE_MARKET_ARTICLE]

            results = fetch_market_news(api_key="test_key")

        record = results[0]
        for field in ("source", "title", "content", "url", "published_at", "known_at", "content_hash"):
            assert field in record, f"Missing field: {field}"


class TestFetchAndStore:
    def test_returns_inserted_count(self):
        """fetch_and_store returns the number of records inserted."""
        mock_store = MagicMock()
        mock_store.insert_articles.return_value = 5

        with patch("src.data.fetchers.finnhub_fetcher.fetch_company_news", return_value=[{}] * 3), \
             patch("src.data.fetchers.finnhub_fetcher.fetch_market_news", return_value=[{}] * 2):
            count = fetch_and_store(
                store=mock_store,
                api_key="test_key",
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert count == 5
        mock_store.insert_articles.assert_called_once()

    def test_returns_zero_when_no_articles(self):
        """fetch_and_store returns 0 when no articles are fetched."""
        mock_store = MagicMock()

        with patch("src.data.fetchers.finnhub_fetcher.fetch_company_news", return_value=[]), \
             patch("src.data.fetchers.finnhub_fetcher.fetch_market_news", return_value=[]):
            count = fetch_and_store(
                store=mock_store,
                api_key="test_key",
                from_date="2026-01-01",
                to_date="2026-04-05",
            )

        assert count == 0
        mock_store.insert_articles.assert_not_called()
