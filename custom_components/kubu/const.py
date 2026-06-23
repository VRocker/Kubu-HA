"""Constants for the Kubu integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "kubu"

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

DEFAULT_NAME = "Kubu"
DEFAULT_API_BASE_URL = "https://api.kubusmart.com"

CONF_API_BASE_URL = "api_base_url"
CONF_SCAN_INTERVAL_SECONDS = "scan_interval_seconds"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_TYPE = "token_type"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

SENSOR_KEY_OPEN = "is_open"
SENSOR_KEY_LOCKED = "is_locked"
SENSOR_KEY_BATTERY = "battery"
