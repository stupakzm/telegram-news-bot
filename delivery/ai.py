import json
import logging
import os
import requests
import google.generativeai as genai

GEMINI_PRIMARY = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT_TEMPLATE = """\
You are a news summarizer for a Telegram bot. Analyze the articles below and return a JSON array.

For each article return an object with exactly these keys:
- "url": the article url (unchanged from input)
- "title": the article title (unchanged from input)
- "summary": 2-3 punchy sentences for a tech-savvy reader
- "hashtags": JSON array of 1-2 hashtags chosen from: {hashtag}
- "is_important": true ONLY if major real-world impact (regulation, market crash, critical breach, major launch); false otherwise
- "importance_detail": if is_important true, one paragraph of context; else empty string ""

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
    Falls back: Gemini 2.5 Flash → Gemini 3.5 Flash → Groq Llama.
    Returns [] if all providers fail.
    """
    if not articles:
        return []

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
            return attempt()
        except Exception as e:
            logging.warning("AI provider %s failed: %s", name, e)
            continue

    return []
