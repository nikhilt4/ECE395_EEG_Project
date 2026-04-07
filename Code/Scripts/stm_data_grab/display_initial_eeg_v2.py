import serial
import time
from collections import deque
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

PORT = "COM5"
BAUD = 460800
FS = 250

NUM_SAMPLES = 1000          # rolling plot window
READS_PER_FRAME = 60        # serial reads per animation update
UPDATE_MS = 50

# Heuristic thresholds for raw ADS counts
# These are just rough live-contact indicators, not medical thresholds.
FLAT_RMS_THRESH = 2000
NOISY_RMS_THRESH = 2000000
SATURATION_THRESH = 8000000

ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(2)
ser.reset_input_buffer()
ser.reset_output_buffer()

# Tell STM to start streaming
ser.write(b"START\n")
ser.flush()

x_buf = deque(maxlen=NUM_SAMPLES)
c3_buf = deque(maxlen=NUM_SAMPLES)
cz_buf = deque(maxlen=NUM_SAMPLES)
c4_buf = deque(maxlen=NUM_SAMPLES)
ch4_buf = deque(maxlen=NUM_SAMPLES)

fig, ax = plt.subplots(figsize=(13, 7))
line_c3, = ax.plot([], [], label="C3")
line_cz, = ax.plot([], [], label="Cz")
line_c4, = ax.plot([], [], label="C4")
line_ch4, = ax.plot([], [], label="CH4")

ax.set_title("Live Raw EEG from STM32WB55 / ADS1299")
ax.set_xlabel("Frame Count")
ax.set_ylabel("ADS1299 Raw Counts")
ax.grid(True)
ax.legend(loc="upper right")

status_text = fig.text(0.02, 0.95, "", fontsize=10, va="top", family="monospace")

def rms(vals):
    if len(vals) == 0:
        return 0.0
    arr = np.asarray(vals, dtype=np.float64)
    arr = arr - np.mean(arr)
    return float(np.sqrt(np.mean(arr ** 2)))

def channel_status(name, buf):
    if len(buf) < 50:
        return f"{name}: waiting"

    arr = np.asarray(buf, dtype=np.float64)
    r = rms(arr)
    peak = np.max(np.abs(arr))

    if peak >= SATURATION_THRESH:
        return f"{name}: SATURATING"
    if r < FLAT_RMS_THRESH:
        return f"{name}: TOO FLAT / poor contact?"
    if r > NOISY_RMS_THRESH:
        return f"{name}: VERY NOISY / motion or bad contact?"
    return f"{name}: ok  rms={int(r)}"

def update(frame):
    for _ in range(READS_PER_FRAME):
        try:
            raw = ser.readline()
            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            parts = line.split(",")

            # Data line format from current firmware:
            # D,frame_count,timestamp_ms,C3,Cz,C4,CH4
            if parts[0] == "D" and len(parts) == 7:
                frame_count = int(parts[1])
                timestamp_ms = int(parts[2])   # parsed but not used
                c3 = int(parts[3])
                cz = int(parts[4])
                c4 = int(parts[5])
                ch4 = int(parts[6])

                x_buf.append(frame_count)
                c3_buf.append(c3)
                cz_buf.append(cz)
                c4_buf.append(c4)
                ch4_buf.append(ch4)

            elif parts[0] == "I":
                print("[STM]", ",".join(parts[1:]))

            elif parts[0] == "E":
                print("[EVENT]", ",".join(parts[1:]))

        except ValueError:
            continue
        except Exception as e:
            print("Read error:", e)
            break

    if len(x_buf) == 0:
        return line_c3, line_cz, line_c4, line_ch4

    line_c3.set_data(x_buf, c3_buf)
    line_cz.set_data(x_buf, cz_buf)
    line_c4.set_data(x_buf, c4_buf)
    line_ch4.set_data(x_buf, ch4_buf)

    ax.set_xlim(x_buf[0], x_buf[-1])

    all_vals = list(c3_buf) + list(cz_buf) + list(c4_buf) + list(ch4_buf)
    y_min = min(all_vals)
    y_max = max(all_vals)

    if y_min == y_max:
        y_min -= 1
        y_max += 1

    margin = max(1000, int(0.1 * (y_max - y_min)))
    ax.set_ylim(y_min - margin, y_max + margin)

    status_lines = [
        channel_status("C3 ", c3_buf),
        channel_status("Cz ", cz_buf),
        channel_status("C4 ", c4_buf),
        channel_status("CH4", ch4_buf),
    ]
    status_text.set_text("\n".join(status_lines))

    return line_c3, line_cz, line_c4, line_ch4

ani = FuncAnimation(fig, update, interval=UPDATE_MS, blit=False)

try:
    plt.show()
finally:
    try:
        ser.write(b"STOP\n")
        ser.flush()
        time.sleep(0.2)
    except Exception:
        pass

    ser.close()
    print("Serial port closed.")