from unittest.mock import MagicMock, patch

import pytest

from delivery.extract import feed_ships_stubs, fetch_article_text, _prose


# --- which feeds get followed ----------------------------------------------

def test_hn_is_a_stub_feed():
    assert feed_ships_stubs("https://news.ycombinator.com/rss") is True


def test_ordinary_feeds_are_not_followed():
    assert feed_ships_stubs("https://blogs.nvidia.com/feed") is False
    assert feed_ships_stubs("https://www.phoronix.com/rss.php") is False


def test_malformed_feed_url_is_not_a_stub_feed():
    assert feed_ships_stubs("not a url") is False


# --- prose extraction -------------------------------------------------------

def test_extracts_paragraph_text():
    html = (
        "<html><body><nav>Home About Contact</nav>"
        "<p>" + ("Real article prose about GPUs and CUDA kernels. " * 4) + "</p>"
        "<footer>copyright</footer></body></html>"
    )
    out = _prose(html)
    assert "Real article prose" in out
    assert "copyright" not in out
    assert "Home About Contact" not in out


def test_drops_script_and_style_content():
    html = (
        "<html><body><script>var x = 'tracking pixel garbage';</script>"
        "<style>.cls { color: red; }</style>"
        "<p>" + ("Genuine body text that is long enough to survive. " * 4) + "</p>"
        "</body></html>"
    )
    out = _prose(html)
    assert "tracking pixel" not in out
    assert "color: red" not in out
    assert "Genuine body text" in out


def test_short_paragraphs_are_skipped_as_boilerplate():
    html = "<html><body><p>Share this</p><p>Cookie notice</p></body></html>"
    # No paragraph clears the length bar, so the fallback strip runs; either way
    # the result must not be long enough to be treated as an article.
    assert len(_prose(html)) < 200


# --- fetch behaviour --------------------------------------------------------

def _resp(body: str, ctype="text/html", status=200):
    r = MagicMock()
    r.status_code = status
    r.headers = {"Content-Type": ctype}
    r.encoding = "utf-8"
    r.raw.read.return_value = body.encode()
    r.raise_for_status.return_value = None
    return r


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=True)
@patch("delivery.extract.requests.get")
def test_returns_prose_on_success(mock_get, mock_val, mock_lim):
    html = "<html><body><p>" + ("Long article text about Linux kernels. " * 8) + "</p></body></html>"
    mock_get.return_value = _resp(html)
    out = fetch_article_text("https://example.com/post", 20000)
    assert out is not None
    assert "Long article text" in out


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=False)
@patch("delivery.extract.requests.get")
def test_unsafe_url_is_not_fetched(mock_get, mock_val, mock_lim):
    # HN links point at arbitrary domains, so SSRF validation must gate the GET.
    assert fetch_article_text("http://169.254.169.254/latest/meta-data", 20000) is None
    mock_get.assert_not_called()


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=True)
@patch("delivery.extract.requests.get", side_effect=Exception("connection reset"))
def test_never_raises_on_fetch_failure(mock_get, mock_val, mock_lim):
    # A miss must cost the user nothing; caller falls back to the feed body.
    assert fetch_article_text("https://example.com/post", 20000) is None


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=True)
@patch("delivery.extract.requests.get")
def test_non_html_is_skipped(mock_get, mock_val, mock_lim):
    mock_get.return_value = _resp("%PDF-1.4 ...", ctype="application/pdf")
    assert fetch_article_text("https://example.com/paper.pdf", 20000) is None


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=True)
@patch("delivery.extract.requests.get")
def test_thin_page_returns_none(mock_get, mock_val, mock_lim):
    # A JS shell yields almost no text — treat as a miss, not a valid body.
    mock_get.return_value = _resp("<html><body><div id='root'></div></body></html>")
    assert fetch_article_text("https://example.com/spa", 20000) is None


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=True)
@patch("delivery.extract.requests.get")
def test_output_is_capped(mock_get, mock_val, mock_lim):
    html = "<html><body><p>" + ("words " * 20000) + "</p></body></html>"
    mock_get.return_value = _resp(html)
    out = fetch_article_text("https://example.com/long", 500)
    assert out is not None and len(out) == 500


@patch("delivery.extract._LIMITER")
@patch("delivery.extract.validate_rss_url", return_value=True)
@patch("delivery.extract.requests.get")
def test_rate_limiter_is_acquired(mock_get, mock_val, mock_lim):
    html = "<html><body><p>" + ("Article text here for length. " * 8) + "</p></body></html>"
    mock_get.return_value = _resp(html)
    fetch_article_text("https://example.com/post", 20000)
    mock_lim.acquire.assert_called_once()
