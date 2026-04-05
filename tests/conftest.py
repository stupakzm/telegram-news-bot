import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_track_bot_message():
    """Auto-mock db.track_bot_message in all tests to prevent real DB calls."""
    with patch("db.client.track_bot_message"):
        yield
