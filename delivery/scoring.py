"""Keyword frequency scoring for article relevance.

Done in code (not via the AI) so it's deterministic, cheap, and transparent —
the user can see exactly which keywords matched and how many times.
"""
import re


def score_article(title: str, body: str, keywords: list[str]) -> tuple[int, dict[str, int]]:
    """
    Count keyword occurrences across (title + body).

    Matching is case-insensitive and uses word boundaries so short keywords like
    "AI" don't accidentally match "AGAIN" or "MAIL". Multi-word keywords like
    "supply chain" work as written.

    Returns (total_score, breakdown) where breakdown is {keyword: count}
    listing only keywords that actually matched at least once.
    """
    if not keywords:
        return 0, {}

    haystack = f"{title}\n{body}"
    breakdown: dict[str, int] = {}
    total = 0

    for kw in keywords:
        kw_stripped = kw.strip()
        if not kw_stripped:
            continue
        # Word boundary only applies when the keyword's edge is itself a word
        # character. Lets terms like "C++", ".NET", "C#" match as users expect.
        start_b = r"\b" if _is_word_char(kw_stripped[0]) else ""
        end_b = r"\b" if _is_word_char(kw_stripped[-1]) else ""
        pattern = re.compile(rf"{start_b}{re.escape(kw_stripped)}{end_b}", re.IGNORECASE)
        count = len(pattern.findall(haystack))
        if count:
            breakdown[kw_stripped] = count
            total += count

    return total, breakdown


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def format_relevance(breakdown: dict[str, int]) -> str:
    """Render breakdown as 'Tesla-12, Autopilot-8, NHTSA-5' (sorted by count desc)."""
    if not breakdown:
        return ""
    sorted_kws = sorted(breakdown.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return ", ".join(f"{kw}-{count}" for kw, count in sorted_kws)
