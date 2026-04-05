import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")


ARTICLE = {
    "url": "https://example.com/article",
    "title": "Big AI Announcement",
    "summary": "OpenAI releases GPT-5. It is very powerful.",
    "hashtags": ["#ai"],
    "is_important": False,
    "importance_detail": "",
}

IMPORTANT_ARTICLE = {**ARTICLE, "is_important": True, "importance_detail": "This changes everything."}


def test_format_post_contains_title_summary_hashtags_link():
    from delivery.poster import format_post
    text = format_post(ARTICLE)
    # Title has no special chars — appears verbatim (inside *bold* markers)
    assert "Big AI Announcement" in text
    # Summary contains "GPT-5." — MarkdownV2 escapes "-" and "." with backslash
    assert "OpenAI releases GPT" in text
    # Hashtag "#" is escaped in MarkdownV2
    assert "ai" in text
    # URL is escaped — dots become "\." but domain is still recognisable
    assert "example" in text and "article" in text


def test_callback_data_fits_telegram_limit():
    from delivery.poster import _url_key
    url = "https://www.theverge.com/2024/01/15/some-very-long-article-title-that-goes-on-and-on"
    key = _url_key(url)
    assert len(f"reaction:up:{key}") <= 64
    assert len(f"reaction:down:{key}") <= 64


def test_url_key_is_deterministic():
    from delivery.poster import _url_key
    url = "https://example.com/article"
    assert _url_key(url) == _url_key(url)


def test_url_key_differs_for_different_urls():
    from delivery.poster import _url_key
    assert _url_key("https://example.com/a") != _url_key("https://example.com/b")


@patch("delivery.poster._send_message")
def test_post_article_sends_one_message_for_normal(mock_send):
    mock_send.return_value = {"message_id": 1}
    from delivery.poster import post_article
    post_article(user_id=123, article=ARTICLE)
    assert mock_send.call_count == 1


@patch("delivery.poster._send_message")
def test_post_article_callback_data_uses_hash_not_url(mock_send):
    mock_send.return_value = {"message_id": 1}
    from delivery.poster import post_article, _url_key
    post_article(user_id=123, article=ARTICLE)
    call_kwargs = mock_send.call_args[1]
    buttons = call_kwargs["reply_markup"]["inline_keyboard"][0]
    up_data = buttons[0]["callback_data"]
    down_data = buttons[1]["callback_data"]
    expected_key = _url_key(ARTICLE["url"])
    assert up_data == f"reaction:up:{expected_key}"
    assert down_data == f"reaction:down:{expected_key}"
    assert ARTICLE["url"] not in up_data  # full URL must not be in callback_data


@patch("delivery.poster._send_message")
def test_post_article_sends_followup_for_important(mock_send):
    mock_send.return_value = {"message_id": 42}
    from delivery.poster import post_article
    post_article(user_id=123, article=IMPORTANT_ARTICLE)
    assert mock_send.call_count == 2
    # second call should reply to first message
    second_call_kwargs = mock_send.call_args_list[1][1]
    assert second_call_kwargs.get("reply_to_message_id") == 42


@patch("delivery.poster.requests.post")
def test_send_message_calls_telegram_api(mock_post):
    mock_post.return_value = MagicMock(json=lambda: {"ok": True, "result": {"message_id": 5}})
    mock_post.return_value.raise_for_status = MagicMock()
    from delivery.poster import _send_message
    result = _send_message(chat_id=123, text="Hello")
    assert mock_post.called
    call_json = mock_post.call_args[1]["json"]
    assert call_json["chat_id"] == 123
    assert call_json["text"] == "Hello"
    assert result["message_id"] == 5
