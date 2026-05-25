"""
Connect to Williwaw BLE device and send a ramp-up (0→9) then ramp-down (9→0)
command sequence, waiting 1 second between each step.

Protocol (observed from btsnoop_hci.log):
  Handle 0x001b — 19-byte command payload
    byte 0 : 0x01  (message type, constant)
    byte 1 : step  (0–9)
    byte 2 : 0x00  (flag)
    bytes 3–18: constant tail
  Williwaw echoes the written value back as a notification on the same handle.
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner

DEVICE_NAME = "Williwaw"
# UUID for the main control characteristic (declaration at 0x001a, value at 0x001b)
CONTROL_CHAR_UUID = "0bc70002-ac91-4a15-ae2d-4fad27e55276"

_TAIL = bytes([0x02, 0x00, 0x00, 0x00, 0x00,
               0x02, 0x00, 0x00, 0x00, 0x00,
               0x01, 0x00, 0x00, 0x00, 0x00, 0x00])


def make_command(step: int) -> bytes:
    return bytes([0x01, step, 0x00]) + _TAIL


def on_notification(char, data: bytearray) -> None:
    print(f"  ← ack  handle=0x{char.handle:04x}  {data.hex()}")


async def ramp(client: BleakClient) -> None:
    steps = list(range(1, 16)) + list(range(15, 0, -1))
    for step in steps:
        cmd = make_command(step)
        print(f"  → step={step:2d}  {cmd.hex()}")
        await client.write_gatt_char(CONTROL_CHAR_UUID, cmd, response=True)
        await asyncio.sleep(5.0)


async def main() -> None:
    print(f"Scanning for '{DEVICE_NAME}'…")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    if device is None:
        print(f"Device '{DEVICE_NAME}' not found. Is it advertising?")
        sys.exit(1)

    print(f"Found: {device.name}  ({device.address})")

    async with BleakClient(device) as client:
        print("Connected.\n")
        await client.start_notify(CONTROL_CHAR_UUID, on_notification)
        await ramp(client)
        await client.stop_notify(CONTROL_CHAR_UUID)

    print("\nDone — disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
