"""
Unit tests for Olist Ingestion Layer (Python).
Tests Frankfurter API rate fetching logic and config parsing.
Usage: uv run pytest tests/
"""

import sys
import os
from unittest.mock import patch, MagicMock
import pytest

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fetch_exchange_rates import fetch_rate_single, fetch_rates_range
from config import get_connection_params


def test_config_connection_params():
    """Test config module parses env vars properly or uses defaults."""
    with patch.dict(os.environ, {"POSTGRES_DB": "test_db", "POSTGRES_PORT": "9999"}):
        params = get_connection_params()
        assert params["dbname"] == "test_db"
        assert params["port"] == 9999


@patch("requests.get")
def test_fetch_rate_single_success(mock_get):
    """Test fetch_rate_single parses a successful API response."""
    # Mock API JSON response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "amount": 1.0,
        "base": "BRL",
        "date": "2018-08-15",
        "rates": {"USD": 0.2588}
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    rate = fetch_rate_single("2018-08-15")
    assert rate == {"2018-08-15": 0.2588}
    mock_get.assert_called_once()


@patch("requests.get")
def test_fetch_rates_range_success(mock_get):
    """Test fetch_rates_range parses a range response correctly."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "amount": 1.0,
        "base": "BRL",
        "start_date": "2018-08-01",
        "end_date": "2018-08-03",
        "rates": {
            "2018-08-01": {"USD": 0.26},
            "2018-08-02": {"USD": 0.258},
            "2018-08-03": {"USD": 0.259}
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    rates = fetch_rates_range("2018-08-01", "2018-08-03")
    assert len(rates) == 3
    assert rates["2018-08-01"] == 0.26
    assert rates["2018-08-02"] == 0.258
    assert rates["2018-08-03"] == 0.259
