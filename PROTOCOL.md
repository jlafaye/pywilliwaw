# Williwaw BLE Protocol

Reverse-engineered from `btsnoop_hci.log` (BTSnoop v1, HCI UART H4).

## Device

| Field | Value |
|---|---|
| Name | `Williwaw` |
| MAC (Android) | `ec:92:6d:a1:2e:7f` |
| Chip | Nordic Semiconductor nRF-series |
| Firmware revision | `Williwaw` (Device Information service) |

## Connection parameters

| Parameter | Value |
|---|---|
| Transport | Bluetooth LE (BLE 4.x / 5.x) |
| Connection interval | 45 ms |
| Supervision timeout | 5 s |
| Security | None (no pairing required) |

---

## GATT services

### GAP — `0x0001–0x0009`

Standard GAP service. Device name is `Williwaw`.

### GATT — `0x000a–0x000d`

Standard GATT service (Service Changed + CCCD).

### Nordic DFU — `0000fe59-0000-1000-8000-00805f9b34fb` (`0x000e–0x0011`)

Nordic Semiconductor DFU service. Not used during normal operation.

### Williwaw control service — `0bc70000-ac91-4a15-ae2d-4fad27e55276` (`0x0012–0x002b`)

The main application service. All fan control happens here.

| Handle | UUID | Properties | Role |
|---|---|---|---|
| `0x0014` | `0bc70001-…` | Write | Command channel (sweep toggle) |
| `0x0017` | `0bc70006-…` | Read, Notify | Status channel |
| `0x001b` | `0bc70002-…` | Read, Write, Notify | Speed / state channel |
| `0x001f` | `0bc70003-…` | Read, Write, Notify | Color / zone config |
| `0x0023` | `0bc70004-…` | Notify | Unknown |
| `0x0027` | `0bc70005-…` | Read | Unknown |
| `0x002a` | `0bc70007-…` | Read, Write | Device name |

### Device Information — `0000180a-0000-1000-8000-00805f9b34fb` (`0x002c–0x002f`)

Standard DIS service. `Firmware Revision String` (`0x002e`) reads as `Williwaw`.

---

## Speed / state characteristic — `0bc70002` (handle `0x001b`)

19-byte payload used for both writes (commands) and notifications (state echo).

```
Byte  0    : 0x01          message type (constant)
Byte  1    : speed         fan speed, 1–15
Byte  2    : sweep         sweep flag, 0x00 = off / 0x01 = on
Bytes 3–7  : 02 00 00 00 00   constant
Bytes 8–12 : 02 00 00 00 00   constant
Bytes 13–18: 01 00 00 00 00 00   constant
```

### Set speed

Write the 19-byte payload to `0bc70002` with `response=True`.

The device echoes the written value back as a notification on the same characteristic, confirming the command was applied.

Example — set speed 5, sweep off:
```
01 05 00 02 00 00 00 00 02 00 00 00 00 01 00 00 00 00 00
```

### State notifications

After any state change (speed write or sweep toggle) the device sends an unsolicited notification on `0bc70002` reflecting the new state. Subscribe to this characteristic to track the current speed and sweep state.

---

## Command characteristic — `0bc70001` (handle `0x0014`)

Single-byte write channel for side-band commands.

| Value | Effect |
|---|---|
| `0x03` | Toggle sweep on/off |

### Toggle sweep

Write `0x03` to `0bc70001`. The device flips the sweep flag and confirms via a notification on `0bc70002` (byte 2 reflects the new state: `0x01` = on, `0x00` = off).

Because this is a **toggle**, track the current sweep state from incoming `0bc70002` notifications and only send the command when the desired state differs from the current state.

---

## Status characteristic — `0bc70006` (handle `0x0017`)

6-byte read/notify characteristic. Sent alongside every `0bc70002` notification.

```
Byte  0    : 0x01   (constant, likely "OK")
Bytes 1–5  : 0x00   (reserved / always zero in observed traffic)
```

No writes observed to this characteristic.

---

## Color / zone config — `0bc70003` (handle `0x001f`)

20-byte read/write characteristic. Not modified during the observed session; initial value on connection:

```
00 00 00 00 00 00 00 ff 00 80  00 00 00 00 00 00 00 ff 00 80
|────────── zone A ──────────| |────────── zone B ──────────|
```

Each 10-byte zone appears to encode an RGB color and brightness. Within the captured value, bytes 7–9 of each zone are `00 ff 00 80`:

| Bytes | Interpretation |
|---|---|
| 0–5 | Unknown / padding |
| 6 | Red (0x00) |
| 7 | Green (0xff) |
| 8 | Blue (0x00) |
| 9 | Brightness (0x80 = 50%) |

---

## Typical connection sequence

1. Central connects (LE Extended Connection, 45 ms interval).
2. Central performs full GATT service discovery.
3. Central reads initial state from `0bc70002` (speed + sweep).
4. Central reads `0bc70003` (color config) and `0bc70007` (device name).
5. Central subscribes (CCCD notify) to `0bc70002` and `0bc70006`.
6. Normal operation: writes to `0bc70002` (speed) and `0bc70001` (sweep toggle).

---

## Observed command examples

```
# Speed 3, sweep off
WriteReq 0x001b  01 03 00 02 00 00 00 00 02 00 00 00 00 01 00 00 00 00 00

# Speed 9, sweep off  (ramp peak)
WriteReq 0x001b  01 09 00 02 00 00 00 00 02 00 00 00 00 01 00 00 00 00 00

# Enable sweep  (sweep was off → byte[2] becomes 0x01 in echo)
WriteReq 0x0014  03
Notif    0x001b  01 03 01 02 00 00 00 00 02 00 00 00 00 01 00 00 00 00 00

# Disable sweep  (sweep was on → byte[2] becomes 0x00 in echo)
WriteReq 0x0014  03
Notif    0x001b  01 03 00 02 00 00 00 00 02 00 00 00 00 01 00 00 00 00 00
```
