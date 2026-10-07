# AromaTech Ambience — BLE protocol

Everything here was measured against one physical Ambience. No vendor
documentation exists. Values marked *inferred* fit every observation but have
not been proven by a targeted test.

MAC addresses below are replaced with `AA:BB:CC:DD:EE:FF`.

## Advertisement

```
name              Ambience
raw               0201060909416d6269656e6365
manufacturer_data {}          (in the advertisement)
service_uuids     []
```

Flags and a complete local name, nothing else. That is why discovery matches
on the name `Ambience*`.

At close range the **scan response** carries manufacturer data:

```
17932 (0x460C): a1 00 29 00 01 00 01 02 00 00 0a <mac:6> 00 da
```

Bytes 11–16 are the device's own MAC. ESPHome Bluetooth proxies forward the
advertisement but not the scan response, so a proxy reports
`manufacturer_data: {}`. An empty value from a proxy scan is not evidence the
device has none, and matching on manufacturer ID would never fire through a
proxy.

## GATT table

```
SERVICE 0000ee01-0000-1000-8000-00805f9b34fb
   CHAR 0000ee02-...  [notify]                + CCCD 2902
   CHAR 0000ee03-...  [write]
SERVICE 0000dd01-0000-1000-8000-00805f9b34fb
   CHAR 0000dd02-...  [notify]                + CCCD 2902
   CHAR 0000dd03-...  [write]
SERVICE 0000cc01-0000-1000-8000-00805f9b34fb
   CHAR 0000cc02-...  [notify]                + CCCD 2902
   CHAR 0000cc03-...  [write]
SERVICE 0000ae00-0000-1000-8000-00805f9b34fb
   CHAR 0000ae01-...  [write-without-response]
   CHAR 0000ae02-...  [notify]                + CCCD 2902
```

The vendor app uses only `EE01`: commands are written to `EE03` (handle
`0x000d`), replies arrive as notifications on `EE02` (handle `0x000a`, CCCD
`0x000b`). `dd01`, `cc01` and `ae00` are never touched. There is no
`fff0`/`fff6`, which is why integrations for other AromaTech models cannot
drive this one.

## Framing

Commands:

```
25 <frag> | ff 01 | <cmd:2 big-endian> | af 00 | <len> | <payload...>
```

`ff 01` and `af 00` never varied in any capture. `<len>` counts the payload
only.

**Fragmentation.** ATT MTU is 23, so a write carries at most 20 bytes. A longer
message continues in a following write that starts `25 02` and holds only the
remaining payload.

Replies use the same layout with two differences: the start byte is a
device-side sequence counter instead of the literal `25`, and bytes 2–3 hold a
message count instead of `ff 01`. A reply is a *batch*:

```
<seq> <frag> | <count:2> | <message>...
<message> = <cmd:2 big-endian> | <kind> | 00 | <len> | <payload>
```

`kind` is `0xaf` for binary payloads and `0xbf` for the two string ones
(firmware version and name).

The sequence counter persists across sessions — observed `5c 5d`, later
`5f`–`62`, later `68 69` — so a client must not assume a starting value. It is
only useful for grouping fragments.

## Commands

| Cmd      | Len | Payload                     | Meaning |
|----------|-----|-----------------------------|---------|
| `0x000a` | 7   | `YY MM DD WD HH MM SS`      | Time sync. The device answers with its whole state. |
| `0x0015` | 2   | `01 00` / `01 01`           | Sound off / on |
| `0x000b` | 6   | `04 RR GG BB <bri> <mode>`  | Light |
| `0x03e9` | 5   | `01 00 00 00 00` / `01 01 00 00 00` | Master power on / off |
| `0x03e9` | 15  | see below                   | Schedule |

`0x03e9` is told apart by payload length: 5 is power, 15 is schedule.

### Power

Verified by actuation: the ON frame written from a laptop with the app closed
made the diffuser spray. Polarity is **inverted between command and reply** —
sending `00` makes the reply report `01` (on). Consistent across eight
exchanges.

### Light

| mode | App label |
|------|-----------|
| 0    | Off       |
| 1    | Warm      |
| 2    | Cool      |
| 3    | Flow      |
| 4    | Custom    |

Only Custom honours the RGB bytes; the presets ignore them. Brightness is
0–100. After Off the device can report RGB `(0, 0, 0)`, so a client turning
the light back on should pick a visible preset rather than Custom black.

### Time sync

`1a 08 1d 06 11 11 1a` decoded to 26-08-29, weekday 6, 17:17:26, matching the
wall clock at capture. Weekday is ISO (Monday = 1).

There is no read-only status command. The time sync is what the vendor app
sends on every connect, and the device answers it with an eight-message batch:
schedule, firmware, name, light, intensity presets and sound. That is the
cheapest honest way to poll.

**The greeting is required.** On a freshly opened link the device acknowledges
writes at the GATT layer but ignores them until it has received a time sync.

### Schedule

As written by the app:

```
01 01 01 01 01 | 82   | 06 00 | 14 00 | 01   | 00 00 00 00
head             days   from    to      int.   tail
```

- **days** — bit 7 is an enable flag, bits 0–6 are days with bit 0 = Sunday
  (*inferred* from the masks `0x7f`, `0xff` and `0x82`, the last while the app
  showed Monday only).
- **from / to** — whole hours, little-endian 16-bit. There is no minutes field.
- **intensity** — 1 to 4 (the app's slider has four positions; 1, 2 and 3 have
  been observed). There is no live intensity command; changing it means
  rewriting the schedule.

The 15-byte payload is sent as two writes: the first fills 20 bytes and
carries the 11 schedule values, then `25 02 00 00 00 00` completes the
four-byte zero tail. **A first-fragment-only write is ignored by the device.**

As reported by the device, the head carries status:

```
01  01  00  01 01  ...
    ^   ^
    |   +-- run code: 0 idle, 2 running, 3 stopped
    +------ current power: 1 on, 0 off
```

A read-modify-write must **not** echo those bytes back. Writing a reported
head such as `01 00 03 ...` as a command asserts "power off, run code 3"; the
vendor app then lost its schedule and further edits stopped sticking. Always
force the head to `01 01 01 01 01`.

Replies to a schedule write declare 15 bytes and carry 11, with no
continuation. A parser that waits for the declared length discards every
confirmation.

Even a correctly framed schedule write is occasionally ignored. The cause is
unconfirmed (BLE timing is suspected). This integration retries up to three
times and confirms each attempt against a fresh device report.

## Not established

- Bytes 3 and 4 of the schedule head (`01 01` in every frame). The app's `+`
  button implies multiple schedule slots; one of these may be a slot index.
- Whether `af 00` is a checksum, a device class or padding. It never varied
  and can be copied verbatim.
- Whether other AromaTech models share the `EE01` protocol.

## Capturing your own traffic

- The AromaTech iOS app runs natively on Apple Silicon Macs, so its BLE goes
  through the Mac's radio.
- PacketLogger captures nothing until Apple's macOS Bluetooth logging profile
  is installed and the Mac rebooted
  (developer.apple.com/bug-reporting/profiles-and-logs).
- `.pklg` records are little-endian: `uint32 length`, `uint32 seconds`,
  `uint32 microseconds`, `uint8 type`, payload. ATT rides on L2CAP CID
  `0x0004`; filter by the diffuser's ACL connection handle.
- The device advertises intermittently. Scan for 45 seconds or more; 15-second
  scans missed it repeatedly.
- ESPHome's `ble_client` and `bluetooth_proxy` do not co-operate on one ESP32,
  so use a laptop with `bleak` to enumerate the GATT table.
