import os
import pytest
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def test_valid_https_url():
    from bot.validation import validate_rss_url
    with patch("bot.validation.socket.getaddrinfo", return_value=[(2, 1, 6, '', ("93.184.216.34", 0))]):
        assert validate_rss_url("https://example.com/feed.xml") is True

def test_valid_http_url():
    from bot.validation import validate_rss_url
    with patch("bot.validation.socket.getaddrinfo", return_value=[(2, 1, 6, '', ("93.184.216.34", 0))]):
        assert validate_rss_url("http://example.com/feed.xml") is True

def test_rejects_ftp_scheme():
    from bot.validation import validate_rss_url
    assert validate_rss_url("ftp://example.com/feed") is False

def test_rejects_192_168_private():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://192.168.1.1/feed") is False

def test_rejects_10_x_private():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://10.0.0.1/feed") is False

def test_rejects_172_16_private():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://172.16.0.1/feed") is False

def test_rejects_loopback():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://127.0.0.1/feed") is False

def test_rejects_link_local():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://169.254.1.1/feed") is False

def test_rejects_cgnat():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://100.64.0.1/feed") is False

def test_rejects_ipv6_loopback():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https://[::1]/feed") is False

def test_rejects_empty_string():
    from bot.validation import validate_rss_url
    assert validate_rss_url("") is False

def test_rejects_no_hostname():
    from bot.validation import validate_rss_url
    assert validate_rss_url("https:///feed") is False
