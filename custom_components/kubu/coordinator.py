"""DataUpdateCoordinator for the Kubu integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KubuApiClient, KubuApiError, KubuAuthError, KubuBleNode
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KubuNodeState:
    """Runtime node state merged from API and BLE updates."""

    node: KubuBleNode
    is_open: bool | None
    is_locked: bool | None
    battery: int | None
    last_seen: datetime | None


class KubuCoordinator(DataUpdateCoordinator[dict[str, KubuNodeState]]):
    """Coordinator handling both API discovery and BLE-fed state changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: KubuApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(days=1),
        )
        self._client = client
        self._node_id_by_mac: dict[str, str] = {}

    async def _async_update_data(self) -> dict[str, KubuNodeState]:
        """Fetch BLE nodes from API."""
        try:
            nodes = await self._client.async_get_ble_nodes()
        except KubuAuthError as err:
            raise ConfigEntryAuthFailed("Kubu authentication failed") from err
        except KubuApiError as err:
            raise UpdateFailed(f"Error fetching Kubu devices: {err}") from err

        updated: dict[str, KubuNodeState] = dict(self.data) if self.data else {}
        updated_index: dict[str, str] = dict(self._node_id_by_mac)

        for node in nodes:
            previous = self.data.get(node.node_id) if self.data else None
            updated[node.node_id] = KubuNodeState(
                node=node,
                is_open=previous.is_open if previous else node.is_open,
                is_locked=previous.is_locked if previous else node.is_locked,
                battery=previous.battery if previous else node.battery,
                last_seen=previous.last_seen if previous else None,
            )
            updated_index[node.mac_address.upper()] = node.node_id

        self._node_id_by_mac = updated_index
        return updated

    def has_known_mac(self, mac_address: str) -> bool:
        """Return whether this MAC belongs to a known node."""
        return mac_address.upper() in self._node_id_by_mac

    def get_dp_key_for_mac(self, mac_address: str) -> str | None:
        """Return dpKey for the node mapped to the given MAC."""
        node_id = self._node_id_by_mac.get(mac_address.upper())
        if not node_id or not self.data:
            return None
        state = self.data.get(node_id)
        return state.node.dp_key if state else None

    def get_sensor_type_for_mac(self, mac_address: str) -> int | None:
        """Return sensor type for the node mapped to the given MAC."""
        node_id = self._node_id_by_mac.get(mac_address.upper())
        if not node_id or not self.data:
            return None
        state = self.data.get(node_id)
        return state.node.sensor_type if state else None

    def async_handle_ble_update(
        self,
        mac_address: str,
        *,
        is_open: bool | None,
        is_locked: bool | None,
        battery: int | None,
        last_seen: datetime,
    ) -> None:
        """Merge a BLE update into coordinator data and fan out listeners."""
        if not self.data:
            return
        node_id = self._node_id_by_mac.get(mac_address.upper())
        if not node_id:
            return

        existing = self.data.get(node_id)
        if existing is None:
            return

        next_state = KubuNodeState(
            node=existing.node,
            is_open=is_open if is_open is not None else existing.is_open,
            is_locked=is_locked if is_locked is not None else existing.is_locked,
            battery=battery if battery is not None else existing.battery,
            last_seen=last_seen,
        )

        merged = dict(self.data)
        merged[node_id] = next_state
        self.async_set_updated_data(merged)
