"""Kubu integration setup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KubuApiClient
from .bluetooth import KubuBluetoothManager
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    CONF_TOKEN_TYPE,
    DEFAULT_API_BASE_URL,
    PLATFORMS,
)
from .coordinator import KubuCoordinator


@dataclass(slots=True)
class KubuRuntimeData:
    """Runtime objects for one config entry."""

    client: KubuApiClient
    coordinator: KubuCoordinator
    bluetooth: KubuBluetoothManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kubu from a config entry."""
    session = async_get_clientsession(hass)

    def _store_token(
        token: str | None,
        token_type: str,
        refresh_token: str | None,
        expires_at: str | None,
    ) -> None:
        updated_data = {
            **entry.data,
            CONF_ACCESS_TOKEN: token,
            CONF_TOKEN_TYPE: token_type,
            CONF_REFRESH_TOKEN: refresh_token,
            CONF_TOKEN_EXPIRES_AT: expires_at,
        }
        hass.config_entries.async_update_entry(entry, data=updated_data)

    def _on_token_updated(
        token: str | None,
        token_type: str,
        refresh_token: str | None,
        expires_at: str | None,
    ) -> None:
        _store_token(token, token_type, refresh_token, expires_at)

    client = KubuApiClient(
        base_url=entry.data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        session=session,
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        token_expires_at=entry.data.get(CONF_TOKEN_EXPIRES_AT),
        on_token_updated=_on_token_updated,
    )

    coordinator = KubuCoordinator(
        hass=hass,
        client=client,
    )
    await coordinator.async_config_entry_first_refresh()

    bluetooth = KubuBluetoothManager(hass, coordinator)
    bluetooth.start()

    entry.runtime_data = KubuRuntimeData(
        client=client,
        coordinator=coordinator,
        bluetooth=bluetooth,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Kubu config entry."""
    runtime: KubuRuntimeData = entry.runtime_data
    runtime.bluetooth.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)
