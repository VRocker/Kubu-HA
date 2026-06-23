"""Kubu sensor platform."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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
    """Set up Kubu battery sensors for every discovered node."""
    runtime: KubuRuntimeData = entry.runtime_data
    coordinator = runtime.coordinator
    await coordinator.async_request_refresh()
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        if not coordinator.data:
            return
        new_entities: list[SensorEntity] = []
        for node_id in coordinator.data:
            if node_id in known:
                continue
            known.add(node_id)
            new_entities.append(KubuBatterySensor(entry.entry_id, coordinator, node_id))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


class KubuBatterySensor(CoordinatorEntity[KubuCoordinator], SensorEntity):
    """Battery percentage sensor for one node."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, entry_id: str, coordinator: KubuCoordinator, node_id: str
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._node_id = node_id
        self._attr_unique_id = f"{entry_id}_{node_id}_battery"

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
            model="BLE Node",
            serial_number=node.serial_number,
            hw_version=f"Type {node.sensor_type}" if node.sensor_type else None,
            connections={(("mac", node.mac_address))} if node.mac_address else None,
        )

    @property
    def native_value(self) -> int | None:
        return self._state.battery

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
