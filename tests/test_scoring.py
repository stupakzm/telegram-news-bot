from delivery.scoring import score_article, format_relevance, _number_variants


def test_counts_per_keyword_total_and_breakdown():
    score, breakdown = score_article(
        title="Tesla recalls 2 million vehicles over Autopilot",
        body="Tesla said NHTSA found Autopilot unsafe. Autopilot is now under review. Tesla stock fell.",
        keywords=["Tesla", "Autopilot", "NHTSA", "EV"],
    )
    # breakdown stays RAW counts — it is what the user is shown.
    assert breakdown == {"Tesla": 3, "Autopilot": 3, "NHTSA": 1}
    assert score > 0


def test_case_insensitive_match():
    score, breakdown = score_article(
        title="EV market grows",
        body="The ev sector boomed; EV adoption was strong.",
        keywords=["EV"],
    )
    assert breakdown == {"EV": 3}
    assert score > 0


def test_word_boundary_skips_substrings():
    score, breakdown = score_article(
        title="AI breakthrough",
        body="The AI revolution again advances. Mail systems lag.",
        keywords=["AI"],
    )
    # 'again' contains 'ai' but only the two standalone 'AI's count
    assert breakdown == {"AI": 2}
    assert score > 0


def test_multi_word_keyword_matches():
    score, breakdown = score_article(
        title="Supply chain risks rise",
        body="A new supply chain audit found gaps. Supply chain resilience is the theme.",
        keywords=["supply chain"],
    )
    assert breakdown == {"supply chain": 3}
    assert score > 0


def test_no_keywords_returns_zero():
    score, breakdown = score_article("anything", "anything", keywords=[])
    assert score == 0
    assert breakdown == {}


def test_no_matches_returns_zero_and_empty():
    score, breakdown = score_article(
        "Stock prices", "Markets are quiet today", keywords=["Tesla", "EV"],
    )
    assert score == 0
    assert breakdown == {}


def test_special_regex_chars_in_keyword_are_escaped():
    # Keyword "C++" must match literally, not blow up the regex engine.
    score, breakdown = score_article(
        title="C++ guide", body="C++ is alive. C++ thrives.", keywords=["C++"],
    )
    assert breakdown == {"C++": 3}
    assert score > 0


# --- title weighting -------------------------------------------------------

def test_title_match_outweighs_body_match():
    in_title, _ = score_article("Tesla wins", "unrelated filler text", ["Tesla"])
    in_body, _ = score_article("Markets today", "Tesla wins big", ["Tesla"])
    assert in_title > in_body


def test_title_hit_beats_several_body_hits():
    # One headline mention should outrank a passing mention repeated in body.
    headline, _ = score_article("Tesla recall", "nothing relevant here", ["Tesla"])
    buried, _ = score_article("Markets today", "Tesla. Tesla. Tesla.", ["Tesla"])
    assert headline > buried


# --- diminishing returns ---------------------------------------------------

def test_repeat_mentions_have_diminishing_returns():
    one, _ = score_article("t", "Tesla", ["Tesla"])
    ten, _ = score_article("t", " ".join(["Tesla"] * 10), ["Tesla"])
    assert ten > one            # more is still better
    assert ten < one * 10       # but far from linear


def test_verbose_article_does_not_swamp_a_focused_one():
    # Under the old raw counting a body with 8 mentions scored 8x a single
    # headline hit. Damping + title weight must bring those close together.
    # (8 body mentions still edges ahead — that is intended, not a bug.)
    focused, _ = score_article("Tesla recalls vehicles", "brief note", ["Tesla"])
    padded, _ = score_article("Markets today", ("filler " * 200) + ("Tesla " * 8), ["Tesla"])
    assert padded < focused * 2


# --- singular/plural -------------------------------------------------------

def test_singular_keyword_matches_plural():
    score, breakdown = score_article("Chip shortage", "New chips shipped.", ["chip"])
    assert breakdown == {"chip": 2}
    assert score > 0


def test_plural_keyword_matches_singular():
    # 'developers' is a real keyword in use; it should find 'developer' too.
    score, breakdown = score_article(
        "developer tools", "Independent developers rejoice.", ["developers"],
    )
    assert breakdown == {"developers": 2}


def test_y_plural_form():
    score, breakdown = score_article("Company news", "Several companies merged.", ["companies"])
    assert breakdown == {"companies": 2}


def test_plural_does_not_apply_to_non_alpha_keywords():
    # "C++" must not sprout a "C++s" variant. Asserted on the variant helper
    # directly: the *matcher* has always been open-ended on the right for
    # non-word-char endings, so "C++" legitimately matches inside "C++s"
    # regardless of pluralisation. That boundary behaviour predates this change.
    assert _number_variants("C++") == ()
    assert _number_variants(".NET") == ()
    assert _number_variants("C#") == ()


# --- acronym aliases -------------------------------------------------------

def test_ai_matches_spelled_out_expansion():
    score, breakdown = score_article(
        title="AI advances",
        body="Artificial intelligence research accelerated this year.",
        keywords=["AI"],
    )
    assert breakdown == {"AI": 2}


def test_ai_does_not_match_machine_learning():
    # ML has its own keyword; AI must not silently absorb it.
    score, breakdown = score_article(
        "Progress", "Machine learning models improved.", ["AI"],
    )
    assert score == 0
    assert breakdown == {}


def test_ml_matches_machine_learning():
    score, breakdown = score_article(
        "ML news", "Machine learning is everywhere.", ["ML"],
    )
    assert breakdown == {"ML": 2}


def test_it_does_not_match_the_pronoun_it():
    # The whole reason acronyms match case-sensitively: a case-insensitive
    # "IT" would hit the pronoun in nearly every sentence.
    score, breakdown = score_article(
        title="Markets today",
        body="It rose, then it fell, and it recovered. It was busy.",
        keywords=["IT"],
    )
    assert score == 0
    assert breakdown == {}


def test_it_matches_real_it_usage():
    score, breakdown = score_article(
        title="IT budgets grow",
        body="Information technology spending rose.",
        keywords=["IT"],
    )
    assert breakdown == {"IT": 2}


# --- formatting (unchanged) ------------------------------------------------

def test_format_relevance_sorts_by_count_descending():
    # Count of 1 renders bare (no "-1" noise); higher counts keep their number.
    out = format_relevance({"Tesla": 3, "Autopilot": 8, "NHTSA": 1})
    assert out == "Autopilot-8, Tesla-3, NHTSA"


def test_format_relevance_empty_returns_empty_string():
    assert format_relevance({}) == ""


def test_format_relevance_tiebreak_alphabetical():
    # Equal counts → alphabetical by lowercased keyword
    out = format_relevance({"Zebra": 2, "Apple": 2})
    assert out == "Apple-2, Zebra-2"


def test_format_relevance_drops_count_of_one():
    # A keyword that matched once appears bare — "-1" carries no signal.
    assert format_relevance({"GPU": 1, "kernel": 1, "Linux": 1}) == "GPU, kernel, Linux"


def test_format_relevance_caps_at_three_keywords():
    out = format_relevance({"A": 9, "B": 8, "C": 7, "D": 6, "E": 5})
    assert out == "A-9, B-8, C-7"


# --- distinct-keyword breadth ----------------------------------------------

def test_distinct_keywords_beat_one_keyword_repeated():
    # Three different terms is a stronger signal than one term three times.
    broad, bd_broad = score_article(
        "GPU news", "NVIDIA shipped CUDA updates.", ["NVIDIA", "CUDA", "GPU"],
    )
    narrow, bd_narrow = score_article(
        "GPU news", "GPU and GPU again.", ["NVIDIA", "CUDA", "GPU"],
    )
    assert len(bd_broad) == 3 and len(bd_narrow) == 1
    assert broad > narrow


def test_single_keyword_gets_no_diversity_bonus():
    # One distinct match must be scored exactly as before the bonus existed.
    import math
    from delivery.scoring import _TITLE_WEIGHT, _SCORE_SCALE
    score, _ = score_article("Tesla", "Tesla", ["Tesla"])
    expected = _TITLE_WEIGHT * math.log2(2) + math.log2(2)
    assert score == round(expected * _SCORE_SCALE)


def test_diversity_bonus_scales_with_distinct_count():
    two, _ = score_article("a", "NVIDIA CUDA", ["NVIDIA", "CUDA", "GPU"])
    three, _ = score_article("a", "NVIDIA CUDA GPU", ["NVIDIA", "CUDA", "GPU"])
    assert three > two
