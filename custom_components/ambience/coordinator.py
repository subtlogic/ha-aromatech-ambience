"""BLE transport and state for the AromaTech Ambience.

Connects on demand rather than holding the link. An ESP32 Bluetooth proxy has
only three connection slots, often shared with locks, lamps and other BLE
devices. Camping a slot for a diffuser is not a fair trade, and a command
taking a second longer is not noticeable on this kind of device.

Refreshing state costs one time-sync write, which is what the vendor app sends
on connect and which the device answers with its entire state. There is no
read-only status command, so this is the cheapest honest way to poll.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import protocol as p
from .const import DISCONNECT_DELAY, REPLY_TIMEOUT, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class AmbienceCoordinator(DataUpdateCoordinator[p.State]):
    """Owns the connection and the last known device state."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Ambience {address}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.address = address
        self._lock = asyncio.Lock()
        self._client: BleakClient | None = None
        self._disconnect_task: asyncio.Task | None = None
        self._reply: asyncio.Future[p.State] | None = None
        self._reassembler = p.Reassembler()

    # ------------------------------------------------------------------ BLE

    @callback
    def _on_notify(self, _handle, data: bytearray) -> None:
        state = self._reassembler.feed(bytes(data))
        if state is None:
            return
        if self._reply is not None and not self._reply.done():
            self._reply.set_result(state)

    async def _connect(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client

        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(
                f"{self.address} was not heard by any Bluetooth proxy recently. "
                "This device advertises intermittently, so a miss is not "
                "necessarily a fault."
            )

        client = await establish_connection(
            BleakClient, device, self.address, max_attempts=3
        )
        await client.start_notify(p.NOTIFY_UUID, self._on_notify)
        self._client = client
        return client

    async def _disconnect_later(self) -> None:
        try:
            await asyncio.sleep(DISCONNECT_DELAY)
        except asyncio.CancelledError:
            return
        async with self._lock:
            client, self._client = self._client, None
            if client is not None and client.is_connected:
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001 - teardown must not raise
                    _LOGGER.debug("disconnect failed, ignoring", exc_info=True)

    def _schedule_disconnect(self) -> None:
        if self._disconnect_task is not None and not self._disconnect_task.done():
            self._disconnect_task.cancel()
        self._disconnect_task = self.hass.async_create_background_task(
            self._disconnect_later(), "ambience-disconnect"
        )

    # -------------------------------------------------------------- commands

    async def _exchange(self, frames: list[bytes]) -> p.State | None:
        """Write one command and return whatever state the device reports."""
        async with self._lock:
            client = await self._connect()
            self._reassembler = p.Reassembler()
            self._reply = self.hass.loop.create_future()
            try:
                for frame in frames:
                    await client.write_gatt_char(p.WRITE_UUID, frame, response=True)
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(self._reply), REPLY_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    # Only the 0x03e9 and time-sync commands were ever seen to
                    # answer. Light and sound appear to be fire-and-forget, so
                    # a timeout here is expected rather than a failure.
                    _LOGGER.debug("no reply within %ss", REPLY_TIMEOUT)
                    return None
            finally:
                self._reply = None
                self._schedule_disconnect()

    async def _command(self, frames: list[bytes]) -> None:
        """Send a command, then refresh so entities reflect the device."""
        reported = await self._exchange(frames)
        if reported is not None and reported.power is not None:
            self.async_set_updated_data(_merge(self.data, reported))
        else:
            await self.async_request_refresh()

    async def async_set_power(self, on: bool) -> None:
        await self._command(p.power(on))

    async def async_set_sound(self, on: bool) -> None:
        await self._command(p.sound(on))

    async def async_set_light(self, mode: int) -> None:
        rgb = self.data.rgb if self.data and self.data.rgb else (0, 0, 0)
        await self._command(p.light(mode, rgb=rgb))

    # --------------------------------------------------------------- polling

    async def _async_update_data(self) -> p.State:
        """Ask for state by doing what the app does on connect.

        A time sync is a write, but it is the write the vendor app itself
        sends every time it connects, and the device answers with its whole
        state. Nothing else in the protocol reads without writing.
        """
        state = await self._exchange(p.sync_time(dt_util.now()))
        if state is None:
            raise UpdateFailed("device did not report state after a time sync")
        return _merge(self.data, state)


def _merge(old: p.State | None, new: p.State) -> p.State:
    """Overlay a partial reply onto what is already known.

    A reply to a power command carries only the 0x03e9 message, so light,
    sound and firmware would otherwise be blanked on every toggle.
    """
    if old is None:
        return new
    merged = p.State(**{**old.__dict__, **{
        k: v for k, v in new.__dict__.items() if v not in (None, {}, [])
    }})
    merged.raw = {**old.raw, **new.raw}
    return merged
