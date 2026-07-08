"""Focused unit tests for pure helpers with tricky edge cases."""
import time

from app.main import _content_disposition
from app.security import _RateLimiter


# ── Content-Disposition header building ──────────────────────────────────────


def test_content_disposition_strips_crlf_injection():
    """A filename containing CRLF must not be able to inject a second header."""
    header = _content_disposition("evil\r\nSet-Cookie: x=1.txt")
    assert "\r" not in header and "\n" not in header
    assert "Set-Cookie" in header  # kept as literal text, not a real header line
    assert header.startswith("attachment;")


def test_content_disposition_strips_quotes_and_backslash():
    header = _content_disposition('a"b\\c.txt')
    # The ASCII fallback field must not contain a bare quote/backslash that
    # would break out of the quoted value.
    ascii_part = header.split('filename="', 1)[1].split('"', 1)[0]
    assert '"' not in ascii_part and "\\" not in ascii_part


def test_content_disposition_non_ascii_uses_rfc5987():
    header = _content_disposition("résumé.pdf")
    assert "filename*=UTF-8''" in header


def test_content_disposition_empty_falls_back_to_download():
    header = _content_disposition("")
    assert 'filename="download"' in header


# ── Rate limiter ─────────────────────────────────────────────────────────────


def test_rate_limiter_allows_then_blocks():
    rl = _RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        rl.check("k")  # first three fine
    try:
        rl.check("k")
        assert False, "4th attempt should have raised"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 429


def test_rate_limiter_evicts_stale_keys():
    """The eviction sweep must reclaim buckets once they age out, so memory
    doesn't grow with every distinct key seen over the process lifetime."""
    rl = _RateLimiter(max_attempts=5, window_seconds=0)  # everything is instantly stale
    rl.check("a")
    rl.check("b")
    time.sleep(0.001)
    rl.check("c")  # sweep on this call should drop the now-expired a/b (and c ages out too)
    assert len(rl._hits) <= 1


def test_rate_limiter_independent_keys():
    rl = _RateLimiter(max_attempts=1, window_seconds=60)
    rl.check("user:1.2.3.4")
    # A different key is unaffected by another key hitting its cap.
    rl.check("user:5.6.7.8")
