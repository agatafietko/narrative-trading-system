"""Tests for fetch_historical_data validation layer."""
from __future__ import annotations

import pytest


def test_validate_fetch_results_passes_when_all_nonzero():
    """validate_fetch_results does not exit when all counts > 0."""
    from scripts.fetch_historical_data import validate_fetch_results
    validate_fetch_results({"yfinance": 715, "fred": 120, "finnhub": 300})


def test_validate_fetch_results_exits_when_yfinance_zero():
    """validate_fetch_results exits 1 when yfinance returns 0 records."""
    from scripts.fetch_historical_data import validate_fetch_results

    with pytest.raises(SystemExit) as exc_info:
        validate_fetch_results({"yfinance": 0, "fred": 120, "finnhub": 300})

    assert exc_info.value.code == 1


def test_validate_fetch_results_exits_when_fred_zero():
    """validate_fetch_results exits 1 when fred returns 0 records."""
    from scripts.fetch_historical_data import validate_fetch_results

    with pytest.raises(SystemExit) as exc_info:
        validate_fetch_results({"yfinance": 715, "fred": 0, "finnhub": 300})

    assert exc_info.value.code == 1


def test_validate_fetch_results_exits_when_finnhub_zero():
    """validate_fetch_results exits 1 when finnhub returns 0 records."""
    from scripts.fetch_historical_data import validate_fetch_results

    with pytest.raises(SystemExit) as exc_info:
        validate_fetch_results({"yfinance": 715, "fred": 120, "finnhub": 0})

    assert exc_info.value.code == 1
