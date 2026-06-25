"""Config flow for the Kubu integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KubuApiClient, KubuApiError, KubuAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_BASE_URL,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_API_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(
            CONF_SCAN_INTERVAL_SECONDS,
            default=int(DEFAULT_SCAN_INTERVAL.total_seconds()),
        ): vol.All(
            int,
            vol.Range(min=30, max=3600),
        ),
    }
)


class KubuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Kubu setup config flow."""

    VERSION = 1
    _reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step shown in the UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = KubuApiClient(
                base_url=DEFAULT_API_BASE_URL,
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
                session=session,
            )
            try:
                await client.async_login()
            except KubuAuthError:
                errors["base"] = "invalid_auth"
            except KubuApiError:
                _LOGGER.exception("Unexpected error authenticating with Kubu")
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Kubu ({user_input[CONF_EMAIL]})",
                    data={
                        **user_input,
                        CONF_API_BASE_URL: DEFAULT_API_BASE_URL,
                        CONF_ACCESS_TOKEN: client.access_token,
                        CONF_TOKEN_EXPIRES_AT: client.token_expires_at,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle an initiated reauth flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(data["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm and execute reauthentication."""
        errors: dict[str, str] = {}

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = KubuApiClient(
                base_url=(
                    self._reauth_entry.data.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL)
                    if self._reauth_entry
                    else DEFAULT_API_BASE_URL
                ),
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
                session=session,
            )
            try:
                await client.async_login()
            except KubuAuthError:
                errors["base"] = "invalid_auth"
            except KubuApiError:
                errors["base"] = "cannot_connect"

            if not errors and self._reauth_entry is not None:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_ACCESS_TOKEN: client.access_token,
                        CONF_TOKEN_EXPIRES_AT: client.token_expires_at,
                    },
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )
