import json
import logging
logger = logging.getLogger(__name__)
import os
import requests
import google.generativeai as genai

GEMINI_PRIMARY = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_ARTICLES_PER_PROMPT = 15  # cap to avoid token/payload limits on all AI providers

PROMPT_TEMPLATE = """\
You are a news summarizer for a Telegram bot delivering tech news to developers and tech-savvy readers.

Analyze the articles below and return a JSON array. Each element must have exactly these keys:

- "url": unchanged from input
- "title": unchanged from input
- "summary": 2-3 sentences. Write in direct, factual style — state what happened, the key details, \
and why it matters. No filler phrases like "In this article", "The author discusses", "This piece covers", \
"Someone explains", or any meta-references to the article itself. Write about the news, not about the article.
- "hashtags": JSON array of 1-2 hashtags chosen from: {hashtag}
- "is_important": true ONLY if major real-world impact (regulation, market crash, critical security breach, \
major product launch affecting millions); false otherwise
- "importance_detail": if is_important true, one paragraph of concrete context (what changed, who is affected, \
what the consequences are); else empty string ""
- "skip": true if the article is affiliate marketing, a sponsored post, a product promotion/review written \
to sell something, or has no real news value; false otherwise

Return ONLY a valid JSON array. No markdown fences, no explanation.

Articles:
{articles_json}
"""


def _build_prompt(articles: list[dict], hashtag: str) -> str:
    slim = [{"url": a["url"], "title": a["title"], "description": a["description"]} for a in articles]
    return PROMPT_TEMPLATE.format(hashtag=hashtag, articles_json=json.dumps(slim, ensure_ascii=False))


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


def summarize_articles(articles: list[dict], hashtag: str) -> list[dict]:
    """
    Summarize articles using AI. Returns list of summary dicts.
    Falls back: Gemini 2.5 Flash → Gemini 2.0 Flash → Groq Llama.
    Affiliate/sponsored articles (skip=true) are filtered out.
    Returns [] if all providers fail.
    """
    if not articles:
        return []

    # Cap article count to prevent token/payload overflow across all AI providers
    articles = articles[:MAX_ARTICLES_PER_PROMPT]
    prompt = _build_prompt(articles, hashtag)

    provider_names = [
        f"Gemini {GEMINI_PRIMARY}",
        f"Gemini {GEMINI_FALLBACK}",
        "Groq",
    ]
    attempts = [
        lambda: _call_gemini(prompt, GEMINI_PRIMARY),
        lambda: _call_gemini(prompt, GEMINI_FALLBACK),
        lambda: _call_groq(prompt),
    ]
    for name, attempt in zip(provider_names, attempts):
        try:
            results = attempt()
            # Filter out affiliate/promotional articles
            return [r for r in results if not r.get("skip")]
        except Exception as e:
            logger.warning("AI provider %s failed: %s", name, e)
            continue

    return []
