"""Bluetooth advertisement manager for Kubu BLE nodes."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_register_callback,
)
from homeassistant.core import HomeAssistant, callback

from .coordinator import KubuCoordinator

_tilt_movable_map: dict[str, bool] = {}

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DecodedBleState:
    """Decoded BLE state from one advertisement."""

    is_open: bool | None
    is_locked: bool | None
    battery: int | None
    last_seen: datetime


class KubuBluetoothManager:
    """Listen to BLE advertisements and merge updates into the coordinator."""

    def __init__(self, hass: HomeAssistant, coordinator: KubuCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._cancel_callback = None

    def start(self) -> None:
        """Start passive BLE scanning callback."""
        LOGGER.info("Starting BLE advertisement callback for Kubu devices")

        @callback
        def _on_advertisement(
            service_info: BluetoothServiceInfoBleak, change: object
        ) -> None:
            mac = service_info.address.upper()

            dp_key = self._coordinator.get_dp_key_for_mac(mac)
            sensor_type = self._coordinator.get_sensor_type_for_mac(mac)
            if not dp_key:
                return

            decoded = decrypt_advertisement(service_info, dp_key, sensor_type, mac)
            if decoded is None:
                return

            self._coordinator.async_handle_ble_update(
                mac,
                is_open=decoded.is_open,
                is_locked=decoded.is_locked,
                battery=decoded.battery,
                last_seen=decoded.last_seen,
            )

        self._cancel_callback = async_register_callback(
            self._hass,
            _on_advertisement,
            BluetoothCallbackMatcher(manufacturer_id=3535),
            BluetoothScanningMode.PASSIVE,
        )

    def stop(self) -> None:
        """Stop BLE callback."""
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None


def decrypt_advertisement(
    service_info: BluetoothServiceInfoBleak,
    dp_key: str,
    sensor_type: int | None,
    node_id: str,
) -> DecodedBleState | None:
    """Decrypt and parse one BLE advertisement packet."""
    encrypted = _extract_payload(service_info)
    if not encrypted:
        return None

    key = _decode_dp_key(dp_key)
    if key is None:
        return None

    plaintext = _decrypt_aes_ecb(encrypted, key)
    if not plaintext:
        return None

    LOGGER.info("Decrypted BLE payload: %s", plaintext.hex())

    parsed = _parse_payload(plaintext, sensor_type, node_id)
    if parsed is None:
        return None

    return DecodedBleState(
        is_open=parsed.get("is_open"),
        is_locked=parsed.get("is_locked"),
        battery=parsed.get("battery"),
        last_seen=datetime.now(tz=UTC),
    )


def _extract_payload(service_info: BluetoothServiceInfoBleak) -> bytes | None:
    if service_info.service_data:
        for payload in service_info.service_data.values():
            if payload:
                return payload
    if service_info.manufacturer_data:
        for payload in service_info.manufacturer_data.values():
            if payload:
                return payload
    return None


def _decode_dp_key(dp_key: str) -> bytes | None:
    stripped = dp_key.strip()

    # Hex encoded key.
    try:
        hex_value = bytes.fromhex(stripped)
    except ValueError:
        hex_value = None
    if hex_value and len(hex_value) in (16, 24, 32):
        return hex_value

    # Base64 encoded key.
    try:
        b64_value = base64.b64decode(stripped, validate=True)
    except Exception:
        b64_value = None
    if b64_value and len(b64_value) in (16, 24, 32):
        return b64_value

    # Raw text key.
    raw = stripped.encode("utf-8")
    if len(raw) in (16, 24, 32):
        return raw

    return None


def _decrypt_aes_ecb(encrypted: bytes, key: bytes) -> bytes | None:
    if len(encrypted) % 16 != 0:
        return None

    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()  # nosec B305 - protocol requires AES-ECB
    padded = decryptor.update(encrypted) + decryptor.finalize()

    if not padded:
        return None
    pad_len = padded[-1]
    if pad_len <= 0 or pad_len > 16:
        return padded
    if padded[-pad_len:] != bytes([pad_len]) * pad_len:
        return padded
    return padded[:-pad_len]


def _parse_payload(
    plaintext: bytes,
    sensor_type: int | None,
    node_id: str,
) -> dict[str, bool | int | None] | None:
    battery_voltage = _get_battery_voltage_from_payload(plaintext)
    if sensor_type is not None:
        state = _parse_sensor_state(plaintext, sensor_type, node_id)
        if state is not None:
            return {
                "is_open": state[0],
                "is_locked": state[1],
                "battery": _get_battery_percent_from_voltage(battery_voltage)
                if battery_voltage is not None
                else 0,
            }

    return None


def _get_battery_percent_from_voltage(voltage: int) -> int | None:
    """Extract battery percentage from voltage."""
    max_voltage = 3000
    min_voltage = 2000

    if voltage < min_voltage:
        return 0
    if voltage > max_voltage:
        return 100

    clamped_voltage = max(min_voltage, min(voltage, max_voltage))

    return int((clamped_voltage - min_voltage) / (max_voltage - min_voltage) * 100)


def _get_battery_voltage_from_payload(plaintext: bytes) -> int | None:
    """Extract battery voltage from decrypted payload."""
    if len(plaintext) < 4:
        return None

    return int.from_bytes(plaintext[2:4], byteorder="big", signed=False)


def _parse_sensor_state(
    plaintext: bytes,
    sensor_type: int,
    node_id: str,
) -> tuple[bool | None, bool | None] | None:
    if len(plaintext) < 10:
        return None

    raw_value = int.from_bytes(plaintext[8:10], byteorder="big", signed=False)
    state = _evaluate_sensor_state(sensor_type, raw_value, node_id)
    if state is None:
        return None

    return _sensor_state_to_flags(state)


def _sensor_state_to_flags(state: str) -> tuple[bool | None, bool | None]:
    if state == "open":
        return True, False
    if state == "locked":
        return False, True
    return False, False


def _evaluate_sensor_state(
    sensor_type: int,
    raw_value: int,
    node_id: str,
) -> str | None:
    if sensor_type == 2:
        value = raw_value & 63
        return "open" if value in {55, 59, 63} else "closed"
    if sensor_type == 3:
        return "open" if ((raw_value >> 6) & 1) == 1 else "closed"
    if sensor_type == 4:
        return _evaluate_type4(raw_value)
    if sensor_type == 5:
        return _evaluate_type5(raw_value)
    if sensor_type == 8:
        return _evaluate_type8(raw_value)
    if sensor_type == 9:
        return _evaluate_type9(raw_value, node_id)
    if sensor_type == 10:
        return _evaluate_type10(raw_value, node_id)
    if sensor_type in {40, 41}:
        return _evaluate_type40_or_41(raw_value)
    return None


def _evaluate_type4(raw_value: int) -> str:
    i2 = raw_value & 63
    i3 = raw_value & 3
    i4 = (i2 >> 2) & 3
    i5 = (i2 >> 4) & 3

    if i2 == 63:
        return "open"

    if not (i3 == 3 and i4 == 3) and i5 == 3:
        return "closed"

    if i3 == 3 or i5 == 3:
        return "tampered" if (i3 != 3 or i5 == 3) else "secure"

    return "closed"


def _evaluate_type5(raw_value: int) -> str:
    i6 = raw_value & 63
    i7 = raw_value & 3
    i8 = (i6 >> 2) & 3
    i9 = (i6 >> 4) & 3

    if i6 == 63:
        return "open"

    if not (i9 == 3 and i8 == 3) and i7 == 3:
        return "closed"

    if i9 == 3 or i7 == 3:
        return "tampered" if (i9 != 3 or i7 == 3) else "secure"

    return "closed"


def _evaluate_type8(raw_value: int) -> str:
    value = raw_value & 63
    if value in {42, 43, 46}:
        return "locked"
    if value in {58, 59, 62}:
        return "closed"
    return "open" if value == 63 else "tampered"


def _evaluate_type9(raw_value: int, node_id: str) -> str:
    value = raw_value & 255
    critical_value = {253, 225, 245, 181, 213, 149, 229, 165}
    reset_value = {247, 183, 231, 167, 219, 155, 217, 241, 251, 187, 249, 185}
    toggle_value = {
        215,
        151,
        223,
        159,
        246,
        182,
        230,
        166,
        214,
        150,
        222,
        158,
        254,
        190,
        218,
        154,
        192,
        186,
    }
    open_value = {235, 171, 234, 170, 233, 169, 239, 175, 237, 173, 191, 255}

    if value != 255 or not _get_tilt_movable(node_id):
        if value in critical_value:
            _set_tilt_movable(node_id, False)
            return "secure"

        if value in toggle_value:
            _set_tilt_movable(node_id, True)
        elif value not in reset_value:
            return "open" if value in open_value else "tampered"
        else:
            _set_tilt_movable(node_id, False)

    return "tilt"


def _evaluate_type10(raw_value: int, node_id: str) -> str:
    value = raw_value & 255
    secure_set = {235, 171, 234, 170, 233, 169, 239, 175, 237, 173, 191}
    reset_set = {183, 231, 167, 219, 155, 217, 241, 251, 187, 249, 185}
    toggle_set = {
        215,
        151,
        223,
        159,
        246,
        182,
        230,
        166,
        214,
        150,
        222,
        158,
        254,
        190,
        218,
        154,
        192,
        186,
    }
    open_set = {253, 225, 245, 181, 213, 149, 229, 165, 247, 255}

    if value != 255 or not _get_tilt_movable(node_id):
        if value in secure_set:
            _set_tilt_movable(node_id, False)
            return "secure"

        if value in toggle_set:
            _set_tilt_movable(node_id, True)
        elif value not in reset_set:
            return "open" if value in open_set else "tampered"
        else:
            _set_tilt_movable(node_id, False)

    return "tilt"


def _evaluate_type40_or_41(raw_value: int) -> str:
    value = raw_value & 255
    return {
        1: "open",
        2: "closed",
        3: "secure",
    }.get(value, "unknown")


def _get_tilt_movable(node_id: str) -> bool:
    return _tilt_movable_map.get(node_id, False)


def _set_tilt_movable(node_id: str, value: bool) -> None:
    _tilt_movable_map[node_id] = value


def _coerce_bool(*values) -> bool | None:
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


def _coerce_int(*values) -> int | None:
    for value in values:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None
