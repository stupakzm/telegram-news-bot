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
    assert "Big AI Announcement" in text
    assert "OpenAI releases GPT-5" in text
    assert "#ai" in text
    assert "https://example.com/article" in text


@patch("delivery.poster._send_message")
def test_post_article_sends_one_message_for_normal(mock_send):
    mock_send.return_value = {"message_id": 1}
    from delivery.poster import post_article
    post_article(user_id=123, article=ARTICLE)
    assert mock_send.call_count == 1


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
