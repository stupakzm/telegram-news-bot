"""Tests for delivery/poster.py — post formatting, the source·age line, and
the per-digest 'why this matters' follow-up gate."""
import os
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")

import delivery.poster as poster
from delivery.poster import (
    format_post,
    post_article,
    _source_domain,
    _relative_age,
    _source_line,
)

ARTICLE = {
    "url": "https://www.openai.com/index/some-post",
    "title": "Big AI Announcement",
    "summary": "OpenAI releases GPT-5. It is very powerful.",
    "relevance": "AI-3, OpenAI",
    "is_important": False,
    "importance_detail": "",
    "published_at": 0,
}
IMPORTANT_ARTICLE = {**ARTICLE, "is_important": True, "importance_detail": "This changes everything."}


# --- format_post ------------------------------------------------------------

def test_format_post_contains_title_summary_link():
    text = format_post(ARTICLE)
    assert "Big AI Announcement" in text
    assert "OpenAI releases GPT" in text  # summary body present (MDV2 escapes the dash)
    assert "some-post" in text            # url is not MDV2-escaped


def test_format_post_shows_source_domain_without_www():
    text = format_post(ARTICLE)
    assert "openai.com" in text
    assert "www\\.openai\\.com" not in text  # www stripped


def test_format_post_shows_age_when_published_at_known():
    import time
    article = {**ARTICLE, "published_at": int(time.time()) - 3 * 3600}
    text = format_post(article)
    assert "3h ago" in text


# --- source line helpers ----------------------------------------------------

def test_source_domain_strips_www():
    assert _source_domain("https://www.theverge.com/x/y") == "theverge.com"
    assert _source_domain("https://blogs.nvidia.com/blog/z") == "blogs.nvidia.com"


def test_relative_age_buckets():
    now = 1_000_000
    assert _relative_age(now - 10, now) == "just now"
    assert _relative_age(now - 120, now) == "2m ago"
    assert _relative_age(now - 3 * 3600, now) == "3h ago"
    assert _relative_age(now - 2 * 86400, now) == "2d ago"


def test_relative_age_missing_or_future_is_blank():
    assert _relative_age(0) == ""
    assert _relative_age(9_999_999_999, 1_000_000) == ""


def test_source_line_omits_age_when_undated():
    line = _source_line("https://openai.com/x", 0)
    assert "openai" in line
    assert "·" not in line  # no age separator when undated


# --- follow-up gating -------------------------------------------------------

@patch("delivery.poster._send_message")
def test_post_article_sends_one_message_for_normal(mock_send):
    mock_send.return_value = {"message_id": 1}
    post_article(user_id=123, article=ARTICLE)
    assert mock_send.call_count == 1


@patch("delivery.poster._send_message")
def test_post_article_sends_followup_for_important(mock_send):
    mock_send.return_value = {"message_id": 42}
    post_article(user_id=123, article=IMPORTANT_ARTICLE)
    assert mock_send.call_count == 2
    second_kwargs = mock_send.call_args_list[1]
    assert second_kwargs.kwargs.get("reply_to_message_id") == 42


@patch("delivery.poster._send_message")
def test_post_article_suppresses_followup_when_disallowed(mock_send):
    mock_send.return_value = {"message_id": 42}
    post_article(user_id=123, article=IMPORTANT_ARTICLE, allow_followup=False)
    # only the main message goes out; the follow-up is gated off
    assert mock_send.call_count == 1
