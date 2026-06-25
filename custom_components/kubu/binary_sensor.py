"""Kubu binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import KubuRuntimeData
from .const import DOMAIN
from .coordinator import KubuCoordinator


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kubu binary sensors for every discovered node."""
    runtime: KubuRuntimeData = entry.runtime_data
    coordinator = runtime.coordinator
    await coordinator.async_request_refresh()
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        if not coordinator.data:
            return
        new_entities: list[BinarySensorEntity] = []
        for node_id in coordinator.data.keys():
            if node_id in known:
                continue
            known.add(node_id)
            new_entities.append(
                KubuOpenBinarySensor(entry.entry_id, coordinator, node_id)
            )
            new_entities.append(
                KubuLockedBinarySensor(entry.entry_id, coordinator, node_id)
            )
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


class KubuBinaryBase(CoordinatorEntity[KubuCoordinator], BinarySensorEntity):
    """Base class for Kubu binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, entry_id: str, coordinator: KubuCoordinator, node_id: str
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._node_id = node_id

    @property
    def _state(self):
        return self.coordinator.data[self._node_id]

    @property
    def device_info(self) -> DeviceInfo:
        node = self._state.node
        return DeviceInfo(
            identifiers={(DOMAIN, node.node_id)},
            name=node.name,
            manufacturer="Kubu",
            model=node.hardware_name,
            serial_number=node.serial_number,
            hw_version=node.hw_version,
            sw_version=node.fw_version,
            connections={(("mac", node.mac_address))} if node.mac_address else None,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class KubuOpenBinarySensor(KubuBinaryBase):
    """Open/Closed binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_translation_key = "is_open"

    def __init__(
        self, entry_id: str, coordinator: KubuCoordinator, node_id: str
    ) -> None:
        super().__init__(entry_id, coordinator, node_id)
        self._attr_unique_id = f"{entry_id}_{node_id}_is_open"

    @property
    def is_on(self) -> bool | None:
        return self._state.is_open


class KubuLockedBinarySensor(KubuBinaryBase):
    """Locked/Unlocked binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_translation_key = "is_locked"

    def __init__(
        self, entry_id: str, coordinator: KubuCoordinator, node_id: str
    ) -> None:
        super().__init__(entry_id, coordinator, node_id)
        self._attr_unique_id = f"{entry_id}_{node_id}_is_locked"

    @property
    def is_on(self) -> bool | None:
        if self._state.is_locked is None:
            return None
        return not self._state.is_locked
