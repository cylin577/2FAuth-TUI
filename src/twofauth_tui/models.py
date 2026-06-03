from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Account:
    id: int
    service: str
    account: str
    otp_type: str
    digits: int | None = None
    period: int | None = None
    counter: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Account":
        return cls(
            id=int(data["id"]),
            service=str(data.get("service", "")),
            account=str(data.get("account", "")),
            otp_type=str(data.get("otp_type", "")),
            digits=_as_int(data.get("digits")),
            period=_as_int(data.get("period")),
            counter=_as_int(data.get("counter")),
        )


@dataclass(slots=True)
class Otp:
    password: str
    otp_type: str
    generated_at: int | None = None
    period: int | None = None
    counter: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Otp":
        return cls(
            password=str(data.get("password", "")),
            otp_type=str(data.get("otp_type", "")),
            generated_at=_as_int(data.get("generated_at")),
            period=_as_int(data.get("period")),
            counter=_as_int(data.get("counter")),
        )


@dataclass(slots=True)
class AccountView:
    account: Account
    otp: Otp | None = None
    expires_at: int | None = None

    @property
    def label(self) -> str:
        if self.account.service and self.account.account:
            return f"{self.account.service} / {self.account.account}"
        return self.account.service or self.account.account or f"Account {self.account.id}"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
