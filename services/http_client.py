"""
HTTP client utilities with rate limiting and exponential backoff.

Provides resilient HTTP requests with:
- Automatic retries with exponential backoff
- Rate limiting to avoid API quota exhaustion
- Timeout handling
- Request deduplication for caching
"""
import asyncio
import random
import time
from typing import Optional, Any
from collections import defaultdict

import httpx


# ─── Rate Limiter ─────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Simple token bucket rate limiter.

    Usage:
        limiter = RateLimiter(calls_per_second=2)
        async with limiter:
            await client.get(url)
    """

    def __init__(self, calls_per_second: float = 1.0, burst: int = 5):
        self.calls_per_second = calls_per_second
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.calls_per_second)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.calls_per_second
                await asyncio.sleep(wait_time)
                self.tokens = 0

            self.tokens -= 1
        return self

    async def __aexit__(self, *args):
        pass


# ─── Retry Configuration ──────────────────────────────────────────────────────

DEFAULT_RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,
    "max_delay": 30.0,
    "exponential_base": 2,
    "jitter": True,
}

# Status codes that should trigger a retry
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _calculate_delay(attempt: int, base_delay: float, max_delay: float, exponential_base: float, jitter: bool) -> float:
    """Calculate delay with exponential backoff and optional jitter."""
    delay = base_delay * (exponential_base ** attempt)
    if jitter:
        delay = random.uniform(delay * 0.5, delay * 1.5)
    return min(delay, max_delay)


async def request_with_retry(
    method: str,
    url: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    max_retries: int = DEFAULT_RETRY_CONFIG["max_retries"],
    base_delay: float = DEFAULT_RETRY_CONFIG["base_delay"],
    max_delay: float = DEFAULT_RETRY_CONFIG["max_delay"],
    exponential_base: float = DEFAULT_RETRY_CONFIG["exponential_base"],
    jitter: bool = DEFAULT_RETRY_CONFIG["jitter"],
    retryable_status_codes: Optional[set[int]] = None,
    **kwargs: Any,
) -> httpx.Response:
    """
    Make an HTTP request with exponential backoff retry logic.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: URL to request
        client: Optional existing httpx.AsyncClient (creates one if not provided)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        retryable_status_codes: Status codes that trigger a retry
        **kwargs: Additional arguments passed to httpx

    Returns:
        httpx.Response object

    Raises:
        httpx.RequestError: If all retries fail
    """
    if retryable_status_codes is None:
        retryable_status_codes = RETRYABLE_STATUS_CODES

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
        close_client = True

    try:
        last_exception: Optional[Exception] = None
        last_response: Optional[httpx.Response] = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)

                # Check if status code is retryable
                if response.status_code in retryable_status_codes and attempt < max_retries:
                    delay = _calculate_delay(attempt, base_delay, max_delay, exponential_base, jitter)
                    await asyncio.sleep(delay)
                    continue

                # Check for rate limit header and wait if present
                if response.status_code == 429 and attempt < max_retries:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                            await asyncio.sleep(wait_time)
                            continue
                        except ValueError:
                            pass

                    # Fallback to exponential backoff
                    delay = _calculate_delay(attempt, base_delay, max_delay, exponential_base, jitter)
                    await asyncio.sleep(delay)
                    continue

                return response

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError) as e:
                last_exception = e
                if attempt < max_retries:
                    delay = _calculate_delay(attempt, base_delay, max_delay, exponential_base, jitter)
                    await asyncio.sleep(delay)
                continue

        # All retries exhausted
        if last_exception:
            raise last_exception
        if last_response:
            last_response.raise_for_status()
        raise httpx.RequestError("All retries exhausted")

    finally:
        if close_client:
            await client.aclose()


# ─── Pre-configured rate limiters for specific APIs ───────────────────────────

# Google Maps Places API: 100 requests per 100 seconds (1 req/s sustained)
google_maps_limiter = RateLimiter(calls_per_second=1.0, burst=10)

# Claude API: Much higher limits but be conservative
claude_limiter = RateLimiter(calls_per_second=5.0, burst=20)

# DuckDuckGo: No official API, be very conservative
duckduckgo_limiter = RateLimiter(calls_per_second=0.5, burst=3)

# Generic web scraping limiter
scraper_limiter = RateLimiter(calls_per_second=2.0, burst=5)


# ─── Convenience wrappers for specific APIs ───────────────────────────────────

async def google_maps_request(
    url: str,
    params: Optional[dict] = None,
    **kwargs: Any,
) -> httpx.Response:
    """Make a Google Maps API request with rate limiting and retry."""
    async with google_maps_limiter:
        return await request_with_retry("GET", url, params=params, **kwargs)


async def claude_request(
    url: str = "https://api.anthropic.com/v1/messages",
    method: str = "POST",
    headers: Optional[dict] = None,
    **kwargs: Any,
) -> httpx.Response:
    """Make a Claude API request with rate limiting and retry."""
    default_headers = {
        "x-api-key": kwargs.pop("api_key", None),
        "anthropic-version": "2023-06-01",
    }
    if headers:
        default_headers.update(headers)

    async with claude_limiter:
        return await request_with_retry(method, url, headers=default_headers, **kwargs)
