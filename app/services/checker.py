from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.models.monitor import Monitor
from app.services.rules import evaluate_http_response


TRANSIENT_STATUS_CODES = {429, 502, 503, 504}


@dataclass(slots=True)
class CheckExecutionResult:
    success: bool
    reason: str
    status_code: int | None
    latency_ms: int | None
    error_type: str | None
    error_message: str | None
    response_excerpt: str | None


class WebsiteChecker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": self.settings.checker_user_agent},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def run(self, monitor: Monitor) -> CheckExecutionResult:
        attempts = 1 + max(0, self.settings.transient_retry_attempts)

        for attempt in range(attempts):
            response: httpx.Response | None = None
            started = time.perf_counter()
            try:
                response = await self._client.request(
                    monitor.method,
                    monitor.url,
                    timeout=monitor.timeout_seconds or self.settings.checker_default_timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                body_text = response.text or ""
                excerpt = body_text[: self.settings.checker_max_response_chars]

                success, reason = evaluate_http_response(
                    status_code=response.status_code,
                    body_text=body_text,
                    expected_min=monitor.expected_status_min,
                    expected_max=monitor.expected_status_max,
                    content_substring=monitor.content_substring,
                )

                if (
                    not success
                    and response.status_code in TRANSIENT_STATUS_CODES
                    and attempt < attempts - 1
                ):
                    await asyncio.sleep(self.settings.transient_retry_backoff_seconds)
                    continue

                return CheckExecutionResult(
                    success=success,
                    reason=reason,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error_type=None,
                    error_message=None,
                    response_excerpt=excerpt,
                )

            except httpx.TimeoutException as exc:
                if attempt < attempts - 1:
                    await asyncio.sleep(self.settings.transient_retry_backoff_seconds)
                    continue
                return CheckExecutionResult(
                    success=False,
                    reason="request_timeout",
                    status_code=response.status_code if response else None,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error_type="timeout",
                    error_message=str(exc),
                    response_excerpt=None,
                )
            except httpx.RequestError as exc:
                if attempt < attempts - 1:
                    await asyncio.sleep(self.settings.transient_retry_backoff_seconds)
                    continue
                return CheckExecutionResult(
                    success=False,
                    reason="request_error",
                    status_code=response.status_code if response else None,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    response_excerpt=None,
                )

        return CheckExecutionResult(
            success=False,
            reason="unknown_checker_error",
            status_code=None,
            latency_ms=None,
            error_type="unknown",
            error_message="Checker exited without a result",
            response_excerpt=None,
        )
