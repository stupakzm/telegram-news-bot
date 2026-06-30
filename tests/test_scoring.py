from delivery.scoring import score_article, format_relevance


def test_counts_per_keyword_total_and_breakdown():
    score, breakdown = score_article(
        title="Tesla recalls 2 million vehicles over Autopilot",
        body="Tesla said NHTSA found Autopilot unsafe. Autopilot is now under review. Tesla stock fell.",
        keywords=["Tesla", "Autopilot", "NHTSA", "EV"],
    )
    assert score == 7
    assert breakdown == {"Tesla": 3, "Autopilot": 3, "NHTSA": 1}


def test_case_insensitive_match():
    score, breakdown = score_article(
        title="EV market grows",
        body="The ev sector boomed; EV adoption was strong.",
        keywords=["EV"],
    )
    assert score == 3
    assert breakdown == {"EV": 3}


def test_word_boundary_skips_substrings():
    score, breakdown = score_article(
        title="AI breakthrough",
        body="The AI revolution again advances. Mail systems lag.",
        keywords=["AI"],
    )
    # 'again' contains 'ai' but only the two standalone 'AI's count
    assert score == 2
    assert breakdown == {"AI": 2}


def test_multi_word_keyword_matches():
    score, breakdown = score_article(
        title="Supply chain risks rise",
        body="A new supply chain audit found gaps. Supply chain resilience is the theme.",
        keywords=["supply chain"],
    )
    assert score == 3
    assert breakdown == {"supply chain": 3}


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
    assert score == 3
    assert breakdown == {"C++": 3}


def test_format_relevance_sorts_by_count_descending():
    out = format_relevance({"Tesla": 3, "Autopilot": 8, "NHTSA": 1})
    assert out == "Autopilot-8, Tesla-3, NHTSA-1"


def test_format_relevance_empty_returns_empty_string():
    assert format_relevance({}) == ""


def test_format_relevance_tiebreak_alphabetical():
    # Equal counts → alphabetical by lowercased keyword
    out = format_relevance({"Zebra": 2, "Apple": 2})
    assert out == "Apple-2, Zebra-2"
