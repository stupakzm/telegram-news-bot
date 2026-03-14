import pytest
from unittest.mock import patch, MagicMock
import json
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")


SAMPLE_ARTICLES = [
    {"url": "https://a.com/1", "title": "AI Regulation Passed", "description": "EU passes major AI act."},
    {"url": "https://b.com/2", "title": "New GPU Released", "description": "NVIDIA releases RTX 9090."},
]

EXPECTED_SUMMARIES = [
    {
        "url": "https://a.com/1",
        "title": "AI Regulation Passed",
        "summary": "The EU just passed landmark AI legislation.",
        "hashtags": ["#ai"],
        "is_important": True,
        "importance_detail": "This affects all AI companies operating in Europe.",
    },
    {
        "url": "https://b.com/2",
        "title": "New GPU Released",
        "summary": "NVIDIA launches RTX 9090 with massive performance gains.",
        "hashtags": ["#hardware"],
        "is_important": False,
        "importance_detail": "",
    },
]


@patch("delivery.ai._call_gemini", return_value=EXPECTED_SUMMARIES)
def test_summarize_uses_gemini_first(mock_gemini):
    from delivery.ai import summarize_articles
    result = summarize_articles(SAMPLE_ARTICLES, "#ai")
    assert mock_gemini.called
    assert result == EXPECTED_SUMMARIES


@patch("delivery.ai._call_groq", return_value=EXPECTED_SUMMARIES)
@patch("delivery.ai._call_gemini", side_effect=Exception("quota exceeded"))
def test_summarize_falls_back_to_groq_when_gemini_fails(mock_gemini, mock_groq):
    from delivery.ai import summarize_articles
    result = summarize_articles(SAMPLE_ARTICLES, "#ai")
    assert mock_groq.called
    assert result == EXPECTED_SUMMARIES


@patch("delivery.ai._call_groq", side_effect=Exception("groq down"))
@patch("delivery.ai._call_gemini", side_effect=Exception("quota exceeded"))
def test_summarize_returns_empty_when_all_fail(mock_gemini, mock_groq):
    from delivery.ai import summarize_articles
    result = summarize_articles(SAMPLE_ARTICLES, "#ai")
    assert result == []


def test_summarize_uses_gemini_35_before_groq():
    """Gemini 2.5 fails → Gemini 3.5 succeeds → Groq never called."""
    call_count = {"n": 0}

    def gemini_side_effect(prompt, model_name):
        call_count["n"] += 1
        if model_name == "gemini-2.5-flash":
            raise Exception("quota exceeded")
        return EXPECTED_SUMMARIES  # gemini-3.5-flash succeeds

    with patch("delivery.ai._call_gemini", side_effect=gemini_side_effect) as mock_g, \
         patch("delivery.ai._call_groq") as mock_groq:
        from delivery.ai import summarize_articles
        result = summarize_articles(SAMPLE_ARTICLES, "#ai")

    assert result == EXPECTED_SUMMARIES
    assert call_count["n"] == 2  # called twice: 2.5-flash (fail) then 3.5-flash (success)
    assert not mock_groq.called


def test_build_prompt_contains_articles_and_hashtag():
    from delivery.ai import _build_prompt
    prompt = _build_prompt(SAMPLE_ARTICLES, "#ai")
    assert "#ai" in prompt
    assert "AI Regulation Passed" in prompt
    assert "New GPU Released" in prompt
