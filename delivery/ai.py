"""AI summarization for selected articles.

Relevance is scored in code via delivery/scoring.py — the model only writes
the per-article summary plus optional "why this matters" context for major
items. Same 3-provider fallback as before.
"""
import json
import logging
import os

import google.generativeai as genai
import requests

logger = logging.getLogger(__name__)

GEMINI_PRIMARY = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_ARTICLES_PER_PROMPT = 30  # plenty of room: top-K is bounded by URL count × 2

PROMPT_TEMPLATE = """\
You are a news summarizer for a Telegram bot delivering tech news to developers \
and tech-savvy readers.

Summarize the articles below and return a JSON array. Each element must have \
exactly these keys:

- "url": unchanged from input
- "title": unchanged from input
- "summary": 2-3 sentences. Direct, factual — state what happened, key details, \
why it matters. No filler like "In this article", "The author discusses", "This \
piece covers", or other meta-references to the article itself. Write about the \
news, not about the article.
- "is_important": true if the article has significant real-world impact worth a \
deeper explanation — major regulation/policy change, market-moving event, \
critical security breach or zero-day, significant AI model/product release, \
major OSS milestone, notable acquisition or shutdown, important research \
breakthrough. Use true generously for anything a developer or tech reader would \
want to understand in depth; false for routine updates and minor news.
- "importance_detail": if is_important true, 2-3 sentences of concrete context \
(what changed, who is affected, consequences); else empty string ""
- "skip": true if the article is affiliate marketing, sponsored content, a \
product promotion/review written to sell something, or has no real news value; \
false otherwise.

Return ONLY a valid JSON array. No markdown fences, no explanation.

Articles:
{articles_json}
"""


def _build_prompt(articles: list[dict]) -> str:
    slim = [
        {"url": a["url"], "title": a["title"], "body": a.get("body", "")[:2000]}
        for a in articles
    ]
    return PROMPT_TEMPLATE.format(articles_json=json.dumps(slim, ensure_ascii=False))


def _parse_response(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _configure_genai() -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        genai.configure(api_key=key)


_configure_genai()


def _call_gemini(prompt: str, model_name: str) -> list[dict]:
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return _parse_response(response.text)


def _call_groq(prompt: str) -> list[dict]:
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return _parse_response(resp.json()["choices"][0]["message"]["content"])


def summarize_articles(articles: list[dict]) -> list[dict]:
    """
    Summarize selected articles in a single batch call.

    Input: list of {url, title, body}.
    Returns: list of {url, title, summary, is_important, importance_detail}
    with skip=true entries filtered out. Returns [] if all providers fail.
    """
    if not articles:
        return []

    articles = articles[:MAX_ARTICLES_PER_PROMPT]
    prompt = _build_prompt(articles)

    providers = [
        (f"Gemini {GEMINI_PRIMARY}", lambda: _call_gemini(prompt, GEMINI_PRIMARY)),
        (f"Gemini {GEMINI_FALLBACK}", lambda: _call_gemini(prompt, GEMINI_FALLBACK)),
        ("Groq", lambda: _call_groq(prompt)),
    ]
    for name, attempt in providers:
        try:
            results = attempt()
            return [r for r in results if not r.get("skip")]
        except Exception as e:
            logger.warning("AI provider %s failed: %s", name, e)
            continue
    return []
