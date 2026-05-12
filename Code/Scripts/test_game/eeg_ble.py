"""
eeg_ble.py — Shared BLE bridge for the EEG game scripts.

Replaces the per-script `eeg_serial_thread` with a BLE equivalent that
puts the same items into the same queues, so the rest of each game
script does not need to change.

Decision characteristic payload (5 bytes, little-endian):
    int16  ratio_x10000     -- ratio * 10000, range roughly -10000..+10000
    uint8  cls              -- 0 = REST, 1 = LEFT, 2 = RIGHT
    uint16 window_idx       -- monotonic window counter

Status characteristic payload (17 bytes, little-endian):
    uint8  type             -- 0 = baseline_progress, 1 = baseline_done,
                                2 = info
    uint8  progress_n       -- baseline step counter (0 if unused)
    uint8  progress_total   -- baseline total (0 if unused)
    char[14] msg            -- null-padded ASCII string

Command characteristic (write, 1 byte):
    0x00 = STOP
    0x01 = START
    0x02 = RECALIBRATE

Replace the UUIDs below with the ones you set in CubeMX Custom BLE.
"""

import asyncio
import struct
import threading
import queue
from bleak import BleakScanner, BleakClient

# ─────────────────────────────────────────────
#  CONFIG — edit these to match your firmware
# ─────────────────────────────────────────────
DEVICE_NAME = "EEG_Classifier"

DECISION_UUID = "0000fe41-cc7a-482a-984a-7f2ed5b3e58f"
STATUS_UUID   = "0000fe42-cc7a-482a-984a-7f2ed5b3e58f"
COMMAND_UUID  = "0000fe43-cc7a-482a-984a-7f2ed5b3e58f"

CMD_STOP        = 0x00
CMD_START       = 0x01
CMD_RECALIBRATE = 0x02

# ─────────────────────────────────────────────
#  Module-level state shared with the games
# ─────────────────────────────────────────────
_stop_evt   = threading.Event()
_send_queue: "queue.Queue[int]" = queue.Queue()   # commands to send to MCU
_loop_ref   = [None]   # holds the asyncio loop so other threads can poke it


def stop():
    """Signal the BLE thread to disconnect and exit."""
    _stop_evt.set()


def send_command(cmd_byte: int):
    """Thread-safe: queue a command byte to write to the MCU."""
    _send_queue.put(cmd_byte)


def send_recalibrate():
    send_command(CMD_RECALIBRATE)


# ─────────────────────────────────────────────
#  Notification decoders
# ─────────────────────────────────────────────
def _decode_decision(data: bytes):
    if len(data) < 5:
        return None
    ratio_x10000, cls, window_idx = struct.unpack("<hBH", data[:5])
    ratio = ratio_x10000 / 10000.0
    return ratio, cls, window_idx


def _decode_status(data: bytes):
    if len(data) < 17:
        return None
    msg_type, n, total = struct.unpack("<BBB", data[:3])
    raw_msg = data[3:17]
    msg = raw_msg.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
    return msg_type, n, total, msg


# ─────────────────────────────────────────────
#  BLE worker
# ─────────────────────────────────────────────
async def _ble_worker(eeg_queue, eeg_prob_queue):
    """
    eeg_queue       : items pushed for status / classification events
                      Compatible items:
                        "left", "right"                   (lane_dodge)
                        "baseline_done"                   (lane_dodge)
                        ("baseline_progress", str)        (both)
                        ("baseline_done", None)           (neurofeedback)
                        ("info", str)                     (neurofeedback)
    eeg_prob_queue  : (left_prob, right_prob, ratio, cls)
                      Used by neurofeedback. lane_dodge ignores this queue
                      if it doesn't import it.
    """
    print(f"[BLE] Scanning for {DEVICE_NAME}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)
    if device is None:
        print(f"[BLE] {DEVICE_NAME} not found.")
        print("[BLE] Running without hardware — keyboard-only mode")
        return

    print(f"[BLE] Connecting to {device.address}...")
    async with BleakClient(device) as client:
        print(f"[BLE] Connected.")

        def on_decision(_sender, data: bytearray):
            decoded = _decode_decision(bytes(data))
            if decoded is None:
                return
            ratio, cls, window_idx = decoded

            # Push raw probabilities for the neurofeedback monitor
            left_prob  = max(0.0, min(1.0,  ratio + 0.5))
            right_prob = max(0.0, min(1.0, -ratio + 0.5))
            if eeg_prob_queue is not None:
                eeg_prob_queue.put((left_prob, right_prob, ratio, cls))

            # Push semantic events for lane_dodge
            if cls == 1:
                eeg_queue.put("left")
                print(f"[EEG] LEFT  ratio={ratio:+.4f} idx={window_idx}")
            elif cls == 2:
                eeg_queue.put("right")
                print(f"[EEG] RIGHT ratio={ratio:+.4f} idx={window_idx}")
            else:
                # REST — neurofeedback counts these via prob_queue,
                # lane_dodge ignores
                pass

        def on_status(_sender, data: bytearray):
            decoded = _decode_status(bytes(data))
            if decoded is None:
                return
            msg_type, n, total, msg = decoded
            print(f"[STM] type={msg_type} {n}/{total} '{msg}'")

            if msg_type == 0:   # baseline_progress
                progress_str = f"BASELINE,{n}/{total}"
                # Both formats: lane_dodge expects tuple, neurofeedback too
                eeg_queue.put(("baseline_progress", progress_str))
                eeg_queue.put(("info", progress_str))   # for monitor
            elif msg_type == 1:   # baseline_done
                eeg_queue.put("baseline_done")              # lane_dodge form
                eeg_queue.put(("baseline_done", None))       # monitor form
                eeg_queue.put(("info", "BASELINE_DONE"))
            elif msg_type == 2:   # generic info
                eeg_queue.put(("info", msg))

        # Subscribe
        await client.start_notify(DECISION_UUID, on_decision)
        await client.start_notify(STATUS_UUID,   on_status)

        # Tell the MCU to start streaming
        await client.write_gatt_char(COMMAND_UUID, bytes([CMD_START]))
        print("[BLE] START sent, streaming...")

        try:
            while not _stop_evt.is_set():
                # Drain any queued outbound commands (RECALIBRATE etc.)
                try:
                    while True:
                        cmd = _send_queue.get_nowait()
                        await client.write_gatt_char(
                            COMMAND_UUID, bytes([cmd])
                        )
                        print(f"[BLE] cmd 0x{cmd:02X} sent")
                except queue.Empty:
                    pass

                await asyncio.sleep(0.05)
        finally:
            try:
                await client.write_gatt_char(
                    COMMAND_UUID, bytes([CMD_STOP])
                )
                print("[BLE] STOP sent")
            except Exception:
                pass
            try:
                await client.stop_notify(DECISION_UUID)
                await client.stop_notify(STATUS_UUID)
            except Exception:
                pass
            print("[BLE] Disconnected.")


def _thread_target(eeg_queue, eeg_prob_queue):
    loop = asyncio.new_event_loop()
    _loop_ref[0] = loop
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_ble_worker(eeg_queue, eeg_prob_queue))
    except Exception as e:
        print(f"[BLE] Worker error: {e}")
    finally:
        loop.close()
        _loop_ref[0] = None


def start_ble_thread(eeg_queue, eeg_prob_queue=None):
    """
    Launch the BLE bridge in a background thread.
    Returns the thread object so the caller can join it on shutdown.
    """
    _stop_evt.clear()
    t = threading.Thread(
        target=_thread_target,
        args=(eeg_queue, eeg_prob_queue),
        daemon=True,
    )
    t.start()
    return t
