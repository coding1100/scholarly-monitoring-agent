from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from app.core.config import Settings, get_settings
from app.models.check_result import CheckResult
from app.models.incident import Incident
from app.models.monitor import Monitor


class ClickUpNotifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._enabled = self.settings.clickup_enabled
        self._client: httpx.AsyncClient | None = None

        if self._enabled:
            self._client = httpx.AsyncClient(
                base_url=self.settings.clickup_base_url,
                headers={
                    "Authorization": self.settings.clickup_api_token or "",
                    "Content-Type": "application/json",
                },
                timeout=self.settings.clickup_timeout_seconds,
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def send_failure_alert(
        self,
        *,
        monitor: Monitor,
        incident: Incident,
        check_result: CheckResult,
    ) -> str | None:
        if not self._enabled:
            return None

        channel_id = await self._resolve_channel_id(incident.clickup_chat_channel_id)
        await self._send_chat_message(
            channel_id=channel_id,
            text=self._build_failure_message(
                monitor=monitor,
                incident=incident,
                check_result=check_result,
            ),
        )
        return channel_id

    async def send_recovery_alert(
        self,
        *,
        monitor: Monitor,
        incident: Incident | None,
        check_result: CheckResult,
    ) -> str | None:
        if not self._enabled:
            return None

        existing_channel_id = incident.clickup_chat_channel_id if incident else None
        channel_id = await self._resolve_channel_id(existing_channel_id)
        await self._send_chat_message(
            channel_id=channel_id,
            text=self._build_recovery_message(
                monitor=monitor,
                incident=incident,
                check_result=check_result,
            ),
        )
        return channel_id

    async def _resolve_channel_id(self, existing_channel_id: str | None) -> str:
        if self.settings.clickup_mode == "channel":
            assert self.settings.clickup_channel_id is not None
            return self.settings.clickup_channel_id

        if existing_channel_id:
            return existing_channel_id

        return await self._create_direct_message_channel()

    async def _create_direct_message_channel(self) -> str:
        assert self.settings.clickup_workspace_id is not None
        assert self.settings.clickup_dm_user_id is not None

        user_ids = self._candidate_user_ids(self.settings.clickup_dm_user_id)
        path = (
            f"/workspaces/{self.settings.clickup_workspace_id}/chat/channels/direct_message"
        )
        payloads: list[dict] = []
        for user_id in user_ids:
            payloads.extend(
                [
                    {"user_ids": [user_id]},
                    {"member_ids": [user_id]},
                    {"participants": [user_id]},
                ]
            )

        response = await self._request_with_payload_fallback("POST", path, payloads)
        channel_id = self._extract_id(response)
        if channel_id is None:
            raise RuntimeError("Could not extract direct message channel id from ClickUp response")
        return channel_id

    async def _send_chat_message(self, *, channel_id: str, text: str) -> None:
        assert self.settings.clickup_workspace_id is not None
        path = (
            f"/workspaces/{self.settings.clickup_workspace_id}/chat/channels/"
            f"{channel_id}/messages"
        )

        payloads = [
            {"message": text},
            {"content": text},
            {"text_content": text},
            {"message": [{"text": text}]},
        ]
        await self._request_with_payload_fallback("POST", path, payloads)

    async def _request_with_payload_fallback(
        self, method: str, path: str, payloads: list[dict]
    ) -> dict:
        last_error: Exception | None = None
        for payload in payloads:
            try:
                return await self._request(method=method, path=path, json=payload)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {400, 415, 422, 500}:
                    raise
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("No payloads provided for request")

    async def _request(self, method: str, path: str, json: dict) -> dict:
        assert self._client is not None

        max_attempts = 3
        for attempt in range(max_attempts):
            response = await self._client.request(method, path, json=json)

            if response.status_code == 429:
                wait_seconds = self._derive_rate_limit_wait(response=response, attempt=attempt)
                await asyncio.sleep(wait_seconds)
                continue

            if response.status_code >= 400:
                message = (
                    f"ClickUp request failed {method} {path} "
                    f"status={response.status_code} body={response.text[:500]}"
                )
                raise httpx.HTTPStatusError(
                    message=message,
                    request=response.request,
                    response=response,
                )

            if not response.content:
                return {}
            return response.json()

        raise RuntimeError("ClickUp rate limit retries exhausted")

    @staticmethod
    def _derive_rate_limit_wait(response: httpx.Response, attempt: int) -> float:
        reset_value = response.headers.get("X-RateLimit-Reset")
        if reset_value:
            try:
                reset = int(reset_value)
                now = int(datetime.now(timezone.utc).timestamp())
                if reset > 10_000_000_000:
                    reset = int(reset / 1000)
                return max(1.0, float(reset - now))
            except ValueError:
                pass

        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except ValueError:
                pass

        return float(2**attempt)

    @staticmethod
    def _extract_id(response: dict) -> str | None:
        if not response:
            return None

        for key in ("id", "channel_id"):
            value = response.get(key)
            if value:
                return str(value)

        channel = response.get("channel")
        if isinstance(channel, dict):
            value = channel.get("id")
            if value:
                return str(value)

        data = response.get("data")
        if isinstance(data, dict):
            value = data.get("id") or data.get("channel_id")
            if value:
                return str(value)

        return None

    @staticmethod
    def _candidate_user_ids(raw_user_id: str) -> list[str | int]:
        ids: list[str | int] = [raw_user_id]
        if raw_user_id.isdigit():
            ids.insert(0, int(raw_user_id))
        return ids

    @staticmethod
    def _build_failure_message(
        *, monitor: Monitor, incident: Incident, check_result: CheckResult
    ) -> str:
        return (
            f"[DOWN] {monitor.name}\n"
            f"URL: {monitor.url}\n"
            f"Incident ID: {incident.id}\n"
            f"Started At: {incident.started_at.isoformat()}\n"
            f"Reason: {check_result.reason}\n"
            f"Status Code: {check_result.status_code}\n"
            f"Error Type: {check_result.error_type}\n"
            f"Error Message: {check_result.error_message}\n"
            f"Latency (ms): {check_result.latency_ms}\n"
        )

    @staticmethod
    def _build_recovery_message(
        *, monitor: Monitor, incident: Incident | None, check_result: CheckResult
    ) -> str:
        incident_id = str(incident.id) if incident else "none"
        resolved_at = (
            incident.resolved_at.isoformat() if incident and incident.resolved_at else "n/a"
        )

        return (
            f"[RECOVERED] {monitor.name}\n"
            f"URL: {monitor.url}\n"
            f"Incident ID: {incident_id}\n"
            f"Resolved At: {resolved_at}\n"
            f"Status Code: {check_result.status_code}\n"
            f"Latency (ms): {check_result.latency_ms}\n"
        )
