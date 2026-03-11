# tests/test_main.py
import pytest
from unittest.mock import patch, MagicMock


@patch("main.save_posted_ids")
@patch("main.post_article")
@patch("main.summarize_articles")
@patch("main.fetch_all_articles")
@patch("main.load_posted_ids")
def test_main_run_posts_articles(
    mock_load, mock_fetch, mock_summarize, mock_post, mock_save
):
    mock_load.return_value = set()
    mock_fetch.return_value = [
        {"url": "https://a.com/1", "title": "T1", "description": "D1", "category": "#ai"},
        {"url": "https://a.com/2", "title": "T2", "description": "D2", "category": "#tech"},
        {"url": "https://a.com/3", "title": "T3", "description": "D3", "category": "#privacy"},
    ]
    mock_summarize.return_value = [
        {"id": "https://a.com/1", "title": "T1", "summary": "S1", "hashtags": ["#ai"], "is_important": False, "importance_detail": ""},
        {"id": "https://a.com/2", "title": "T2", "summary": "S2", "hashtags": ["#tech"], "is_important": False, "importance_detail": ""},
        {"id": "https://a.com/3", "title": "T3", "summary": "S3", "hashtags": ["#privacy"], "is_important": False, "importance_detail": ""},
    ]
    mock_post.return_value = 1

    from main import run
    run(gemini_key="g", groq_key="r", bot_token="t", channel_id="@c")

    assert mock_post.call_count == 3
    mock_save.assert_called_once()


@patch("main.save_posted_ids")
@patch("main.post_article")
@patch("main.summarize_articles")
@patch("main.fetch_all_articles")
@patch("main.load_posted_ids")
def test_main_run_skips_if_no_new_articles(
    mock_load, mock_fetch, mock_summarize, mock_post, mock_save
):
    mock_load.return_value = set()
    mock_fetch.return_value = []

    from main import run
    run(gemini_key="g", groq_key="r", bot_token="t", channel_id="@c")

    mock_summarize.assert_not_called()
    mock_post.assert_not_called()
