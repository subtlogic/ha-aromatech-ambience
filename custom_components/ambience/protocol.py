"""Wire protocol for the AromaTech Ambience.

Decoded from PacketLogger captures of the vendor app and verified by writing
frames back to the device, which sprayed. Full notes in `docs/PROTOCOL.md`
at the root of the repository.

Transport framing, commands:

    25 <frag> | ff 01 | <cmd:2 big-endian> | af 00 | <len> | <payload>

Replies use a device-side sequence counter in place of the literal 0x25, and
carry a *batch* rather than a single message:

    <seq> <frag> | <count:2> | <message>...

with each message shaped:

    <cmd:2 big-endian> | <kind> | 00 | <len> | <payload>

`kind` is 0xaf for binary payloads and 0xbf for the two string ones. On
connect, in reply to a time sync, the device volunteers its entire state as
one eight-message batch - schedule, firmware, name, light, intensity presets
and sound. That is the status read, and it costs one harmless write.

ATT MTU is 23, so every write and notification is capped at 20 bytes and
longer messages fragment. This is not optional: the connect batch is 144
bytes across nine fragments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SERVICE_UUID = "0000ee01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ee02-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ee03-0000-1000-8000-00805f9b34fb"

CMD_VERSION = 0x0005
CMD_NAME = 0x0006
CMD_COUNTER = 0x0007
CMD_TIME = 0x000A
CMD_LIGHT = 0x000B
CMD_INTENSITY_PRESETS = 0x000E
CMD_UNKNOWN_0014 = 0x0014
CMD_SOUND = 0x0015
CMD_POWER = 0x03E9  # length 5 is power, length 15 is the schedule

START_CMD = 0x25
DIR_CMD = b"\xff\x01"
CONST_AF = b"\xaf\x00"
MAX_ATT = 20  # MTU 23 minus the 3-byte ATT header

LIGHT_MODES = ["off", "warm", "cool", "flow", "custom"]

# Inverted between command and reply: sending 0x00 turns the device ON, and
# the reply then reports 0x01. Verified across eight exchanges.
POWER_ON_ARG = 0x00
POWER_OFF_ARG = 0x01

# The shape of a schedule write, taken from the app rather than from the
# device's reports. See `schedule_from_raw` for why the two differ.
SCHEDULE_WRITE_HEAD = b"\x01\x01\x01\x01\x01"
SCHEDULE_WRITE_LEN = 11    # what the app actually puts on the wire
SCHEDULE_DECLARED_LEN = 15  # what the app claims in the length byte


# --------------------------------------------------------------- encoding

def encode(cmd: int, payload: bytes, declared_len: int | None = None) -> list[bytes]:
    """Build the ATT writes for one command, fragmenting to the MTU.

    `declared_len` overrides the length byte. Only the schedule needs it, and
    only because the app itself is inconsistent there - see the note in
    `schedule_from_raw`.
    """
    body = (DIR_CMD + cmd.to_bytes(2, "big") + CONST_AF
            + bytes([len(payload) if declared_len is None else declared_len])
            + payload)
    out: list[bytes] = []
    pos, frag = 0, 1
    while True:
        chunk = body[pos: pos + MAX_ATT - 2]
        out.append(bytes([START_CMD, frag]) + chunk)
        pos += len(chunk)
        frag += 1
        if pos >= len(body):
            return out


def power(on: bool) -> list[bytes]:
    return encode(CMD_POWER, bytes([0x01, POWER_ON_ARG if on else POWER_OFF_ARG,
                                    0x00, 0x00, 0x00]))


def sound(on: bool) -> list[bytes]:
    return encode(CMD_SOUND, bytes([0x01, 0x01 if on else 0x00]))


def light(mode: int, rgb: tuple[int, int, int] = (0, 0, 0),
          brightness: int = 0x64) -> list[bytes]:
    """`rgb` only takes effect in `custom`; presets ignore it."""
    if not 0 <= mode < len(LIGHT_MODES):
        raise ValueError(f"light mode out of range: {mode}")
    r, g, b = rgb
    return encode(CMD_LIGHT, bytes([0x04, r, g, b, brightness, mode]))


def sync_time(now: datetime) -> list[bytes]:
    """Sent on connect. The device answers with its full state."""
    return encode(CMD_TIME, bytes([
        now.year % 100, now.month, now.day,
        now.isoweekday(), now.hour, now.minute, now.second,
    ]))


def schedule_from_raw(raw: bytes, *, days_mask: int | None = None,
                      start_hour: int | None = None,
                      end_hour: int | None = None,
                      intensity: int | None = None) -> list[bytes]:
    """Rewrite a schedule frame, changing only the named fields.

    Read-modify-write on the schedule VALUES, but never on the frame's head or
    tail, and that distinction is the whole point of this function.

    The device reports 15 bytes:

        01  01  00  01 01  ff  06 00  14 00  01  00 00 00 00
        ^   ^   ^                                 ^^^^^^^^^^^
        |   |   +-- run code: 0 idle, 2 running, 3 stopped     tail, always zero
        |   +------ current power: 1 on, 0 off
        +---------- constant

    Bytes 1 and 2 are STATUS. The app never writes them - every schedule write
    in the captures opens with a flat `01 01 01 01 01` regardless of what the
    device last reported. An earlier version of this function echoed the whole
    frame back verbatim, which meant writing the device's own status codes into
    a command: a reported `01 00 03 ...` went out as a write claiming power off
    and run code 3. The device took that badly - the vendor app lost the
    schedule entirely and edits stopped sticking.

    The app is also inconsistent about length: it declares 15 and then sends
    only 11 bytes, stopping exactly at the 20-byte MTU rather than continuing
    into a second fragment. The four zero tail bytes are never transmitted. We
    match that byte for byte instead of being tidier than the app, because the
    device's parser is the only opinion that counts here.

    What is genuinely read-modify-write: the mask, hours, and intensity that
    are not being changed carry over from the device's own report, so setting
    one field cannot clobber another.
    """
    if len(raw) < 11:
        raise ValueError(f"schedule payload too short to edit: {len(raw)} bytes")
    out = bytearray(raw[:SCHEDULE_WRITE_LEN])
    out[0:5] = SCHEDULE_WRITE_HEAD
    if days_mask is not None:
        out[5] = days_mask & 0xFF
    if start_hour is not None:
        out[6:8] = int(start_hour).to_bytes(2, "little")
    if end_hour is not None:
        out[8:10] = int(end_hour).to_bytes(2, "little")
    if intensity is not None:
        out[10] = int(intensity) & 0xFF
    return encode(CMD_POWER, bytes(out), declared_len=SCHEDULE_DECLARED_LEN)


# --------------------------------------------------------------- decoding

@dataclass
class State:
    """Everything the device volunteers about itself."""

    power: bool | None = None
    days_mask: int | None = None
    start_hour: int | None = None
    end_hour: int | None = None
    intensity: int | None = None
    light_mode: int | None = None
    rgb: tuple[int, int, int] | None = None
    brightness: int | None = None
    sound: bool | None = None
    firmware: str | None = None
    name: str | None = None
    raw: dict[int, bytes] = field(default_factory=dict)

    @property
    def schedule_enabled(self) -> bool | None:
        """Bit 7 of the day mask. Inferred from three observed masks."""
        return None if self.days_mask is None else bool(self.days_mask & 0x80)

    @property
    def days(self) -> list[str]:
        """Bits 0-6, bit 0 = Sunday. Inferred, not proven."""
        if self.days_mask is None:
            return []
        names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return [n for i, n in enumerate(names) if self.days_mask & (1 << i)]

    @property
    def light_mode_name(self) -> str | None:
        if self.light_mode is None or not 0 <= self.light_mode < len(LIGHT_MODES):
            return None
        return LIGHT_MODES[self.light_mode]


def _apply(state: State, cmd: int, payload: bytes) -> None:
    state.raw[cmd] = payload
    if cmd == CMD_POWER and len(payload) >= 11:
        state.power = payload[1] == 0x01
        state.days_mask = payload[5]
        state.start_hour = int.from_bytes(payload[6:8], "little")
        state.end_hour = int.from_bytes(payload[8:10], "little")
        state.intensity = payload[10]
    elif cmd == CMD_LIGHT and len(payload) >= 6:
        state.rgb = (payload[1], payload[2], payload[3])
        state.brightness = payload[4]
        state.light_mode = payload[5]
    elif cmd == CMD_SOUND and len(payload) >= 2:
        state.sound = payload[1] == 0x01
    elif cmd == CMD_VERSION:
        state.firmware = payload.decode("ascii", "replace").strip("\x00 ")
    elif cmd == CMD_NAME:
        state.name = payload.decode("ascii", "replace").strip("\x00 ")


def _truncated_at_mtu(body: bytes, pos: int, length: int) -> bool:
    """Is a short final message the device stopping at the MTU, or a gap?

    The device truncates rather than fragments, exactly as the app does when it
    writes a schedule: it declares 15 bytes, fills the 20-byte ATT payload, and
    sends nothing more. Refusing to parse those replies is why a schedule edit
    used to show no confirmation and then snap back on the next poll.

    A truncation is only believable when the buffer ends flush against a
    fragment boundary AND this is the last message announced. Anything else is
    a batch still in flight, and returning early there would publish a
    half-read state.
    """
    body_per_fragment = MAX_ATT - 2
    ends_at_boundary = len(body) % body_per_fragment == 0
    return ends_at_boundary and pos + 5 + length > len(body) >= pos + 5


def parse_batch(body: bytes) -> State | None:
    """Parse a reassembled reply body into state.

    Layout is `<count:2>` then that many `<cmd:2><kind><00><len><payload>`
    messages. A single-message reply to a command uses the same shape, so this
    handles both.
    """
    if len(body) < 2:
        return None
    count = int.from_bytes(body[0:2], "big")
    state = State()
    pos, seen = 2, 0
    while pos + 5 <= len(body) and seen < max(count, 1):
        cmd = int.from_bytes(body[pos:pos + 2], "big")
        length = body[pos + 4]
        payload = body[pos + 5: pos + 5 + length]
        if len(payload) < length and not _truncated_at_mtu(body, pos, length):
            break
        _apply(state, cmd, payload)
        pos += 5 + length
        seen += 1
    return state if seen else None


class Reassembler:
    """Joins fragmented notifications into one reply body.

    Fragments are grouped by the reply's leading sequence byte. That counter is
    device-side and persists across sessions - observed 0x45, 0x46, later 0x5c,
    later 0x68 - so it is used only for grouping and never assumed to start
    anywhere.

    A batch does not announce its byte length, only its message count, so
    completeness is decided by successfully parsing that many messages.
    """

    def __init__(self) -> None:
        self._seq: int | None = None
        self._buf = bytearray()

    def feed(self, data: bytes) -> State | None:
        if len(data) < 2:
            return None
        seq, frag = data[0], data[1]
        if frag == 1:
            self._seq = seq
            self._buf = bytearray(data[2:])
        elif seq == self._seq:
            self._buf.extend(data[2:])
        else:
            return None

        body = bytes(self._buf)
        if len(body) < 2:
            return None
        count = int.from_bytes(body[0:2], "big")
        # Only surface state once every announced message is present.
        pos, seen = 2, 0
        while pos + 5 <= len(body) and seen < count:
            length = body[pos + 4]
            if pos + 5 + length > len(body):
                if not _truncated_at_mtu(body, pos, length):
                    return None
                seen += 1
                break
            pos += 5 + length
            seen += 1
        if seen < count:
            return None
        return parse_batch(body)
