from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import Account, AccountView, Otp


class ApiError(RuntimeError):
    pass


def normalize_server_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("Server URL cannot be empty.")
    if "://" not in value:
        value = f"https://{value}"
    parts = urlsplit(value)
    if not parts.netloc:
        raise ValueError(f"Invalid server URL: {raw!r}")
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def api_url(server_url: str, suffix: str) -> str:
    return f"{server_url.rstrip('/')}{suffix}"


@dataclass(slots=True)
class ProbeResult:
    available: bool
    status_code: int | None = None
    message: str = ""


class TwoFAuthClient:
    def __init__(self, server_url: str, token: str | None = None) -> None:
        self.server_url = normalize_server_url(server_url)
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def probe(self) -> ProbeResult:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            try:
                response = await client.get(api_url(self.server_url, "/api/v1/features"))
            except httpx.HTTPError as exc:
                return ProbeResult(False, None, str(exc))
        return ProbeResult(True, response.status_code, response.reason_phrase)

    async def list_accounts(self) -> list[Account]:
        payload = await self._get_json("/api/v1/twofaccounts")
        if not isinstance(payload, list):
            raise ApiError("Unexpected twofaccounts response.")
        return [Account.from_json(item) for item in payload]

    async def get_otp(self, account_id: int) -> Otp:
        payload = await self._get_json(f"/api/v1/twofaccounts/{account_id}/otp")
        if not isinstance(payload, dict):
            raise ApiError("Unexpected OTP response.")
        return Otp.from_json(payload)

    async def load_dashboard(self) -> list[AccountView]:
        accounts = await self.list_accounts()
        views: list[AccountView] = []

        semaphore = asyncio.Semaphore(6)

        async def fetch(account: Account) -> AccountView:
            async with semaphore:
                otp = await self.get_otp(account.id)
            expires_at = None
            if otp.generated_at is not None and otp.period:
                expires_at = otp.generated_at + otp.period
            return AccountView(account=account, otp=otp, expires_at=expires_at)

        results = await asyncio.gather(*(fetch(account) for account in accounts))
        views.extend(results)
        views.sort(key=lambda item: (item.account.service.lower(), item.account.account.lower()))
        return views

    async def validate(self) -> None:
        try:
            await self.list_accounts()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise ApiError("Unauthorized. PAT rejected.") from exc
            raise ApiError(f"API error: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ApiError(str(exc)) from exc

    async def _get_json(self, path: str) -> object:
        async with httpx.AsyncClient(
            base_url=self.server_url,
            timeout=15,
            follow_redirects=True,
            headers=self._headers(),
        ) as client:
            response = await client.get(path)
            if response.status_code == 401:
                raise httpx.HTTPStatusError("Unauthorized", request=response.request, response=response)
            if response.status_code >= 400:
                raise ApiError(f"{response.status_code} {response.reason_phrase}")
            return response.json()
