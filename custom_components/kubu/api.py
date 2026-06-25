"""Kubu API client."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

LOGGER = logging.getLogger(__name__)


class KubuAuthError(Exception):
    """Raised when authentication fails."""


class KubuApiError(Exception):
    """Raised for generic API errors."""


@dataclass(slots=True)
class KubuBleNode:
    """Normalized BLE node returned by the API."""

    node_id: str
    name: str
    serial_number: str | None
    mac_address: str
    entity_id: str | None
    sensor_type: int | None
    dp_key: str | None
    hardware_name: str | None
    hw_version: str | None
    fw_version: str | None
    battery: int | None
    is_open: bool | None
    is_locked: bool | None
    raw: dict[str, Any]


class KubuApiClient:
    """Async client for Kubu cloud endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        email: str,
        password: str,
        session: ClientSession,
        access_token: str | None = None,
        token_expires_at: str | None = None,
        name: str | None = None,
        refresh_token: str | None = None,
        token_type: str = "Bearer",
        on_token_updated: Callable[[str | None, str, str | None, str | None], None]
        | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._session = session
        self._access_token = access_token
        self._refresh_token: str | None = refresh_token
        self._token_expires_at = token_expires_at
        self._on_token_updated = on_token_updated
        self._token_type: str = token_type
        self._name: str | None = name

    @property
    def access_token(self) -> str | None:
        """Return the in-memory access token."""
        return self._access_token

    @property
    def token_expires_at(self) -> str | None:
        """Return ISO timestamp when token expires."""
        return self._token_expires_at

    async def async_login(self) -> None:
        """Authenticate and store token state."""
        url = f"{self._base_url}/oauth/login"
        payload = {"email": self._email, "password": self._password}

        try:
            async with self._session.post(url, json=payload, timeout=20) as response:
                body = await response.text()
                if response.status in (401, 403):
                    raise KubuAuthError("invalid credentials")
                if response.status >= 400:
                    raise KubuApiError(f"login failed with HTTP {response.status}")
        except ClientError as err:
            raise KubuApiError(f"login request failed: {err}") from err

        data = self._parse_json(body)

        name = data.get("name")
        if isinstance(name, str) and name:
            self._name = name
        token = data.get("idToken") or data.get("accessToken")
        if not isinstance(token, str) or not token:
            raise KubuApiError("login response did not include an access token")

        expires_in = data.get("expiresIn")
        expires_at: str | None = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = (
                datetime.now(tz=UTC) + timedelta(seconds=int(expires_in))
            ).isoformat()

        token_type = data.get("tokenType") or "Bearer"
        refresh_token = data.get("refreshToken")
        self._set_token(token, token_type, refresh_token, expires_at)

    async def async_get_ble_nodes(self) -> list[KubuBleNode]:
        """Fetch BLE nodes from the API."""
        LOGGER.debug("Fetching BLE nodes from Kubu API")
        data = await self._async_request(
            "GET",
            "/view/rooms",
            auth_required=True,
            retry_on_auth_failure=True,
        )
        candidates = data.get("bleNodes") or data
        if not isinstance(candidates, list):
            raise KubuApiError("device list response was not a list")

        LOGGER.debug("Found %d BLE nodes in API response", len(candidates))

        nodes: list[KubuBleNode] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_node(item)
            if normalized is not None:
                nodes.append(normalized)

        return nodes

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        auth_required: bool,
        retry_on_auth_failure: bool,
    ) -> dict[str, Any]:
        if auth_required and (not self._access_token or self._is_token_expired()):
            await self.async_login()

        url = f"{self._base_url}{path}"
        headers: dict[str, str] = {}
        if auth_required and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with self._session.request(
                method, url, headers=headers, timeout=20
            ) as response:
                body = await response.text()
                if (
                    response.status in (401, 403)
                    and auth_required
                    and retry_on_auth_failure
                ):
                    await self.async_login()
                    return await self._async_request(
                        method,
                        path,
                        auth_required=auth_required,
                        retry_on_auth_failure=False,
                    )
                if response.status >= 400:
                    raise KubuApiError(f"request failed with HTTP {response.status}")
        except (ClientError, ClientResponseError) as err:
            raise KubuApiError(f"request failed: {err}") from err

        return self._parse_json(body)

    def _set_token(
        self,
        token: str | None,
        token_type: str,
        refresh_token: str | None,
        expires_at: str | None,
    ) -> None:
        self._access_token = token
        self._token_type = token_type
        self._refresh_token = refresh_token
        self._token_expires_at = expires_at
        LOGGER.debug(
            "Token updated: %s, %s, %s, %s",
            token,
            token_type,
            refresh_token,
            expires_at,
        )
        if self._on_token_updated:
            self._on_token_updated(token, token_type, refresh_token, expires_at)

    def _is_token_expired(self) -> bool:
        if not self._token_expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(self._token_expires_at)
        except ValueError:
            return False
        return datetime.now(tz=UTC) >= expires_at

    def _normalize_node(self, payload: dict[str, Any]) -> KubuBleNode | None:
        node_name_raw = payload.get("name")
        if not isinstance(node_name_raw, (str, int)):
            return None

        node_id = str(node_name_raw)
        name = payload.get("name") or payload.get("displayName") or f"Kubu {node_id}"
        serial_number = (
            payload.get("serial") if isinstance(payload.get("serial"), str) else None
        )
        mac_address_raw = (
            payload.get("sNo") if isinstance(payload.get("sNo"), str) else None
        )
        mac_address = self._format_mac_address(mac_address_raw)

        entity_id = (
            payload.get("entityId")
            if isinstance(payload.get("entityId"), str)
            else None
        )
        sensor_type = (
            payload.get("type") if isinstance(payload.get("type"), int) else None
        )
        dp_key = payload.get("dpKey") if isinstance(payload.get("dpKey"), str) else None

        hardware_name = (
            payload.get("class") if isinstance(payload.get("class"), str) else "Unknown"
        )
        hw_version = (
            payload.get("hwRev") if isinstance(payload.get("hwRev"), str) else None
        )
        fw_version = (
            payload.get("fwVer") if isinstance(payload.get("fwVer"), str) else None
        )

        LOGGER.debug(
            "Normalized node: id=%s, name=%s, serial=%s, entity=%s, type=%s, mac=%s",
            node_id,
            name,
            serial_number,
            entity_id,
            sensor_type,
            mac_address,
        )

        return KubuBleNode(
            node_id=node_id,
            name=str(name),
            serial_number=serial_number,
            mac_address=mac_address,
            entity_id=entity_id,
            sensor_type=sensor_type,
            dp_key=dp_key,
            hardware_name=hardware_name,
            hw_version=hw_version,
            fw_version=fw_version,
            battery=None,
            is_open=None,
            is_locked=None,
            raw=payload,
        )

    @staticmethod
    def _format_mac_address(mac_address_raw: str | None) -> str | None:
        if not mac_address_raw:
            return None

        normalized = "".join(char.upper() for char in mac_address_raw if char.isalnum())
        if len(normalized) != 12 or any(
            ch not in "0123456789ABCDEF" for ch in normalized
        ):
            return None

        return ":".join(normalized[i : i + 2] for i in range(0, 12, 2))

    @staticmethod
    def _coerce_bool(*values: Any) -> bool | None:
        for value in values:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "open", "locked", "yes"}:
                    return True
                if lowered in {"0", "false", "closed", "unlocked", "no"}:
                    return False
        return None

    @staticmethod
    def _parse_json(body: str) -> dict[str, Any]:
        if not body:
            return {}
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as err:
            raise KubuApiError("API returned invalid JSON") from err
        if not isinstance(decoded, dict):
            raise KubuApiError("API returned an unexpected payload type")
        return decoded
