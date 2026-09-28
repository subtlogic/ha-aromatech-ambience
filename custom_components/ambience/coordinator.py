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
from collections import deque
from collections.abc import Callable
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import protocol as p
from .const import DISCONNECT_DELAY, REPLY_TIMEOUT, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

# Kept here rather than in const.py so that updating this file alone is a
# complete upgrade. Splitting them across two files once meant a coordinator
# that imported names the deployed const.py did not have, and the integration
# failed to load at all.
CONNECT_ATTEMPTS = 3
TRACE_FRAMES = 24        # roughly two full exchanges
NOTIFY_SETTLE = 0.5      # let the link settle before writing the CCCD
RETRY_BACKOFF = 1.0


class AmbienceCoordinator(DataUpdateCoordinator[p.State]):
    """Owns the connection and the last known device state."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        scan_interval: int = SCAN_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Ambience {address}",
            # The heartbeat. Each tick connects, sends a time sync and
            # disconnects, and the device answers with its whole state - so
            # this is also how a change made in the vendor app, or at the unit
            # itself, gets noticed. Shorter means fresher, at the cost of
            # occupying one of the proxy's three connection slots more often.
            update_interval=timedelta(seconds=scan_interval),
        )
        self.address = address
        self._lock = asyncio.Lock()
        self._client: BleakClient | None = None
        self._disconnect_task: asyncio.Task | None = None
        self._reply: asyncio.Future[p.State] | None = None
        self._reassembler = p.Reassembler()
        self._accumulated: p.State | None = None
        # Surfaced as a sensor attribute. A single "last write" slot was not
        # enough: a command that draws no state-carrying reply ends with
        # async_request_refresh, whose own time sync overwrites the slot before
        # anyone can read it. The command then looks like it never happened.
        # A ring keeps the whole exchange - greeting, command, reply, refresh.
        self.trace: deque[str] = deque(maxlen=TRACE_FRAMES)

    # ------------------------------------------------------------------ BLE

    @callback
    def _on_notify(self, _handle, data: bytearray) -> None:
        """Collect replies, and only finish on one that carries state.

        A command draws TWO replies, not one. The first echoes the command back
        - a time sync returns a single 0x000a message holding the time just
        sent - and the real state arrives immediately after as a separate
        eight-message batch. Resolving on the first reply therefore returns a
        State with every field None, which is precisely what left the entities
        at unknown: the receipt was taken for the answer.

        So replies are merged as they arrive and the wait ends only once
        something usable is present. If nothing usable turns up, the timeout in
        `_exchange` returns whatever accumulated rather than nothing.
        """
        self._trace("RX", bytes(data))
        state = self._reassembler.feed(bytes(data))
        if state is None:
            return
        self._reassembler = p.Reassembler()  # ready for the next reply
        self._accumulated = _merge(self._accumulated, state)

        if not _carries_state(self._accumulated):
            return
        if self._reply is not None and not self._reply.done():
            self._reply.set_result(self._accumulated)

    @callback
    def _trace(self, direction: str, data: bytes) -> None:
        """Record one frame, tagged with the command it belongs to.

        The command byte is what makes the trace readable at a glance: a time
        sync and a schedule write are otherwise two similar-looking blobs, and
        telling them apart is the entire question when an edit does not stick.
        """
        # Both directions put the command at bytes 4-5 of the FIRST fragment
        # only: a write is `25 <frag> ff 01 <cmd:2> ...` and a reply is
        # `<seq> <frag> <count:2> <cmd:2> ...`. Continuation fragments carry no
        # command, so they are left untagged rather than mislabelled.
        cmd = ""
        if len(data) >= 6 and data[1] == 0x01:
            cmd = f" cmd={(data[4] << 8) | data[5]:#06x}"
        stamp = dt_util.utcnow().strftime("%H:%M:%S.%f")[:-3]
        self.trace.append(f"{stamp} {direction}{cmd} {data.hex(' ')}")

    async def _connect(self) -> tuple[BleakClient, bool]:
        """Connect and enable notifications, retrying around GATT error 133.

        Returns the client and whether the link is new, because a new link owes
        the device a greeting before it will accept anything - see `_exchange`.

        Enabling notifications means writing the CCCD at handle 0x000b, and
        through an ESPHome proxy that intermittently fails with ESP32 GATT
        error 133 - a generic failure, usually a stale cached service table or
        a descriptor write issued too soon after the link comes up. It is not a
        protocol fault: the same call succeeds from a native adapter, and the
        vendor app writes the same handle.

        So: settle briefly before subscribing, and on failure drop the
        connection entirely and rediscover services rather than retrying on top
        of a cache that may be what is wrong.
        """
        if self._client is not None and self._client.is_connected:
            return self._client, False

        last_error: Exception | None = None
        for attempt in range(CONNECT_ATTEMPTS):
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise UpdateFailed(
                    f"{self.address} was not heard by any Bluetooth proxy "
                    "recently. This device advertises intermittently, so a "
                    "miss is not necessarily a fault."
                )

            client = await establish_connection(
                BleakClient,
                device,
                self.address,
                max_attempts=2,
                # Rediscover on a retry: a wrong cached handle is a prime
                # suspect for 133, and reusing the cache would repeat it.
                use_services_cache=attempt == 0,
            )
            try:
                await asyncio.sleep(NOTIFY_SETTLE)
                await client.start_notify(p.NOTIFY_UUID, self._on_notify)
            except Exception as err:  # noqa: BLE001 - retried below
                last_error = err
                _LOGGER.debug(
                    "start_notify failed on attempt %s/%s: %s",
                    attempt + 1, CONNECT_ATTEMPTS, err,
                )
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001 - teardown must not raise
                    pass
                await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                continue

            self._client = client
            return client, True

        raise UpdateFailed(
            f"could not enable notifications on {self.address} after "
            f"{CONNECT_ATTEMPTS} attempts: {last_error}"
        )

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

    async def _write_and_wait(
        self, client: BleakClient, frames: list[bytes]
    ) -> p.State | None:
        """Write one command and return whatever state the device reports."""
        self._reassembler = p.Reassembler()
        self._accumulated = None
        self._reply = self.hass.loop.create_future()
        try:
            for frame in frames:
                self._trace("TX", frame)
                await client.write_gatt_char(p.WRITE_UUID, frame, response=True)
            try:
                return await asyncio.wait_for(
                    asyncio.shield(self._reply), REPLY_TIMEOUT
                )
            except asyncio.TimeoutError:
                # Not necessarily a failure: only 0x03e9 and the time sync were
                # ever seen to answer, so light and sound appear to be
                # fire-and-forget. Return anything that did arrive.
                _LOGGER.debug("no usable reply within %ss", REPLY_TIMEOUT)
                return self._accumulated
        finally:
            self._reply = None

    async def _exchange(
        self,
        frames: list[bytes] | None = None,
        *,
        build: Callable[[p.State | None], list[bytes]] | None = None,
        handshake: bool = True,
    ) -> p.State | None:
        """Greet the device if the link is new, then send the command.

        THE GREETING IS NOT OPTIONAL. Every capture of the vendor app opens the
        same way: connect, write a time sync, receive the eight-message state
        batch, and only then send whatever the user asked for. Version 0.3.1
        skipped it - the poll happened to be a time sync, but a schedule edit
        arrived on a freshly opened link with no handshake. The device
        acknowledged the write at the GATT layer and then ignored it: the day
        mask never moved off 0xff across four toggles and fifteen minutes of
        watching, with nothing in the log, because nothing had failed.

        `build` exists for the same reason. A schedule write is a
        read-modify-write, and the bytes it starts from should be the ones the
        greeting just returned, not whatever was cached from the last poll
        half an hour ago.
        """
        async with self._lock:
            client, fresh = await self._connect()
            try:
                current = self.data
                if fresh and handshake:
                    greeting = await self._write_and_wait(
                        client, p.sync_time(dt_util.now())
                    )
                    if _carries_state(greeting):
                        current = _merge(current, greeting)
                        self.async_set_updated_data(current)
                payload = frames if frames is not None else build(current)
                return await self._write_and_wait(client, payload)
            finally:
                self._schedule_disconnect()

    async def _command(
        self,
        frames: list[bytes] | None = None,
        *,
        build: Callable[[p.State | None], list[bytes]] | None = None,
    ) -> None:
        """Send a command, then refresh so entities reflect the device."""
        reported = await self._exchange(frames, build=build)
        if _carries_state(reported):
            self.async_set_updated_data(_merge(self.data, reported))
        else:
            await self.async_request_refresh()

    async def async_set_power(self, on: bool) -> None:
        await self._command(p.power(on))

    async def async_set_sound(self, on: bool) -> None:
        await self._command(p.sound(on))

    async def async_set_light(
        self,
        mode: int,
        rgb: tuple[int, int, int] | None = None,
        brightness: int | None = None,
    ) -> None:
        current = self.data
        if rgb is None:
            rgb = current.rgb if current and current.rgb else (0, 0, 0)
        if brightness is None:
            brightness = current.brightness if current and current.brightness else 0x64
        await self._command(p.light(mode, rgb=rgb, brightness=brightness))

    async def async_set_schedule(
        self,
        *,
        days_mask: int | None = None,
        start_hour: int | None = None,
        end_hour: int | None = None,
        intensity: int | None = None,
    ) -> None:
        """Change one schedule field, preserving everything else byte for byte.

        Refuses to act without a schedule frame from the device. The payload
        opens with five bytes nothing has explained - plausibly a slot index,
        given the app offers multiple schedules - so a frame is only ever
        edited, never constructed. Writing a guessed frame could overwrite a
        working schedule.
        """
        def build(current: p.State | None) -> list[bytes]:
            raw = current.raw.get(p.CMD_POWER) if current else None
            if not raw or len(raw) < 11:
                raise HomeAssistantError(
                    "no schedule has been read from the device yet, so there "
                    "is nothing to safely modify - wait for a refresh and retry"
                )
            return p.schedule_from_raw(
                raw,
                days_mask=days_mask,
                start_hour=start_hour,
                end_hour=end_hour,
                intensity=intensity,
            )

        requested = {
            name: value for name, value in (
                ("days_mask", days_mask),
                ("start_hour", start_hour),
                ("end_hour", end_hour),
                ("intensity", intensity),
            ) if value is not None
        }

        def matches_report() -> bool:
            state = self.data
            return state is not None and all(
                getattr(state, name) == value for name, value in requested.items()
            )

        for attempt in range(2):
            await self._command(build=build)
            # An ACK or service success only proves transport. Confirm the
            # value in a fresh device report before telling HA it was saved.
            if matches_report():
                await self.async_request_refresh()
                if matches_report():
                    return
            if attempt == 0:
                await asyncio.sleep(RETRY_BACKOFF)

        actual = {
            name: getattr(self.data, name) if self.data else None
            for name in requested
        }
        raise HomeAssistantError(
            f"Ambience did not retain schedule change: requested {requested}, "
            f"device reported {actual}"
        )

    # --------------------------------------------------------------- polling

    async def _async_update_data(self) -> p.State:
        """Ask for state by doing what the app does on connect.

        A time sync is a write, but it is the write the vendor app itself
        sends every time it connects, and the device answers with its whole
        state. Nothing else in the protocol reads without writing.
        """
        state = await self._exchange(p.sync_time(dt_util.now()), handshake=False)
        if state is None:
            raise UpdateFailed("device did not report state after a time sync")
        return _merge(self.data, state)


def _carries_state(state: p.State | None) -> bool:
    """Does this reply actually tell us anything about the device?

    Deliberately not `state is not None`. The echo reply parses perfectly well
    into a State object with every field unset, and treating that as an answer
    is the bug this guards against.
    """
    if state is None:
        return False
    return any(v is not None for v in (
        state.power, state.light_mode, state.sound, state.days_mask,
    ))


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
