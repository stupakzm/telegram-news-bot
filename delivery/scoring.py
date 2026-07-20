"""Keyword frequency scoring for article relevance.

Done in code (not via the AI) so it's deterministic, cheap, and transparent —
the user can see exactly which keywords matched and how many times.

Ranking is NOT a raw occurrence count. Two adjustments keep verbose articles
from crowding out tightly relevant short ones:

  * a match in the title counts for more than one buried in the body, and
  * repeat mentions have diminishing returns, so the twelfth "Tesla" adds far
    less than the first.

The user-visible breakdown stays as raw counts — "Tesla-12" should mean the
word appeared twelve times, not report an internal weight.
"""
import math
import re
from functools import lru_cache

# A keyword in the headline is a much stronger relevance signal than the ninth
# mention in paragraph twelve.
_TITLE_WEIGHT = 3

# Damped scores are fractional; scale to keep the DB `score` column an integer
# without collapsing distinct rankings onto the same value.
_SCORE_SCALE = 10

# An article hitting NVIDIA + CUDA + GPU is a far better match than one saying
# "GPU" three times, but plain addition scores those identically. Each keyword
# beyond the first lifts the total by this fraction.
_DIVERSITY_BONUS = 0.25

# Deliberately minimal and unambiguous. "AI" expands ONLY to artificial
# intelligence — machine learning belongs to its own keyword, "ML".
_ALIASES = {
    "AI": ("artificial intelligence",),
    "ML": ("machine learning",),
    "IT": ("information technology",),
}


def score_article(title: str, body: str, keywords: list[str]) -> tuple[int, dict[str, int]]:
    """
    Score an article against the user's keywords.

    Matching is case-insensitive and uses word boundaries so short keywords like
    "AI" don't accidentally match "AGAIN" or "MAIL". Multi-word keywords like
    "supply chain" work as written. Singular/plural forms match each other, and
    the acronyms in _ALIASES also match their spelled-out expansion.

    Returns (total_score, breakdown) where breakdown is {keyword: raw_count}
    listing only keywords that actually matched at least once.
    """
    if not keywords:
        return 0, {}

    breakdown: dict[str, int] = {}
    total = 0.0

    for kw in keywords:
        kw_stripped = kw.strip()
        if not kw_stripped:
            continue

        in_title = _count(kw_stripped, title or "")
        in_body = _count(kw_stripped, body or "")
        raw = in_title + in_body
        if not raw:
            continue

        breakdown[kw_stripped] = raw
        total += _TITLE_WEIGHT * math.log2(1 + in_title) + math.log2(1 + in_body)

    # Breadth of match, not just depth.
    distinct = len(breakdown)
    if distinct > 1:
        total *= 1 + _DIVERSITY_BONUS * (distinct - 1)

    return round(total * _SCORE_SCALE), breakdown


def _count(keyword: str, text: str) -> int:
    """Occurrences of a keyword (and its variants) in text."""
    ci, cs = _patterns(keyword)
    n = 0
    if ci is not None:
        n += len(ci.findall(text))
    if cs is not None:
        n += len(cs.findall(text))
    return n


@lru_cache(maxsize=512)
def _patterns(keyword: str) -> tuple[re.Pattern | None, re.Pattern | None]:
    """Compile (case-insensitive, case-sensitive) matchers for one keyword.

    Bare acronyms are matched case-SENSITIVELY. Without that, a keyword of "IT"
    matches the English pronoun "it" in nearly every sentence and swamps the
    score. Their spelled-out expansions stay case-insensitive.
    """
    ci_forms: set[str] = set()
    cs_forms: set[str] = set()

    upper = keyword.upper()
    if upper in _ALIASES and keyword.isalpha():
        cs_forms.add(upper)
        ci_forms.update(_ALIASES[upper])
    else:
        ci_forms.add(keyword)
        ci_forms.update(_number_variants(keyword))

    return _alternation(ci_forms, re.IGNORECASE), _alternation(cs_forms, 0)


def _alternation(forms: set[str], flags: int) -> re.Pattern | None:
    if not forms:
        return None
    # Longest first so a longer form wins over one that prefixes it.
    ordered = sorted(forms, key=len, reverse=True)
    return re.compile("|".join(_bounded(f) for f in ordered), flags)


def _bounded(form: str) -> str:
    # Word boundary only applies when the form's edge is itself a word
    # character. Lets terms like "C++", ".NET", "C#" match as users expect.
    start_b = r"\b" if _is_word_char(form[0]) else ""
    end_b = r"\b" if _is_word_char(form[-1]) else ""
    return f"{start_b}{re.escape(form)}{end_b}"


def _number_variants(word: str) -> tuple[str, ...]:
    """The other of (singular, plural) for a simple alphabetic word.

    Intentionally naive — no irregulars, no phrases. "chip" finds "chips" and
    "developers" finds "developer"; anything more needs a real stemmer.
    """
    if not word.isalpha() or len(word) < 3:
        return ()

    lower = word.lower()
    if lower.endswith("ies") and len(word) > 4:
        return (word[:-3] + "y",)
    if lower.endswith("ss"):
        return (word + "es",)
    if lower.endswith("s"):
        return (word[:-1],)
    if lower.endswith(("x", "z", "ch", "sh")):
        return (word + "es",)
    return (word + "s",)


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def format_relevance(breakdown: dict[str, int]) -> str:
    """Render breakdown as 'Tesla-12, Autopilot-8, NHTSA-5' (sorted by count desc)."""
    if not breakdown:
        return ""
    sorted_kws = sorted(breakdown.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return ", ".join(f"{kw}-{count}" for kw, count in sorted_kws)
