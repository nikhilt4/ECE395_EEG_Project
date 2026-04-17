import serial
import time
from collections import deque
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy.signal import butter, lfilter

PORT = "COM5"
BAUD = 460800
FS = 250

NUM_SAMPLES = 1000
READS_PER_FRAME = 60
UPDATE_MS = 50

# Fixed y-axis range for filtered signal — adjust if needed
YRANGE = 100000

SATURATION_THRESH = 8000000


def wait_for_stm32(ser, timeout=30.0):
    print(f"Waiting for STM32 on {ser.port}... (power on or reset the board now)")
    t_start = time.time()
    while (time.time() - t_start) < timeout:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"[BOOT] {line}")
        if "READY" in line:
            print("STM32 ready.\n")
            return True
    print("Timed out waiting for STM32.")
    return False


def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    b, a = butter(order, [lowcut / nyq, highcut / nyq], btype='band')
    return b, a

def bandpass_filter(data, lowcut=8, highcut=30.0, fs=250):
    arr = np.array(data, dtype=np.float64)
    if len(arr) < 13:
        return arr
    b, a = butter_bandpass(lowcut, highcut, fs)
    return lfilter(b, a, arr)

def contact_quality(buf):
    """
    Returns a color and label based on raw signal RMS.
    Good contact = low stable RMS (small DC drift).
    Poor contact = very high RMS (saturating or noisy).
    No contact = frozen constant value (std ~ 0).
    """
    if len(buf) < 50:
        return "gray", "WAIT"
    arr = np.array(list(buf), dtype=np.float64)
    peak = np.max(np.abs(arr))
    std = np.std(arr)
    rms_60hz = _rms_at_60hz(arr)

    if peak >= SATURATION_THRESH:
        return "red", "SATURATING"
    if std < 500:
        return "red", "FLAT — disconnected?"
    if rms_60hz > 50000:
        return "orange", f"NOISY (60Hz) — poor contact"
    if std < 50000:
        return "green", f"OK  std={int(std)}"
    return "orange", f"MARGINAL  std={int(std)}"

def _rms_at_60hz(arr, fs=250):
    """Estimate 60Hz noise power as proxy for impedance."""
    if len(arr) < fs:
        return 0.0
    nyq = fs / 2.0
    b, a = butter(2, [58/nyq, 62/nyq], btype='band')
    filtered = lfilter(b, a, arr)
    return float(np.sqrt(np.mean(filtered**2)))


ser = serial.Serial(PORT, BAUD, timeout=0.1)
ser.reset_input_buffer()
ser.reset_output_buffer()

wait_for_stm32(ser)
ser.write(b"START\n")
ser.flush()
print("START sent. Streaming...")

x_buf  = deque(maxlen=NUM_SAMPLES)
c3_buf = deque(maxlen=NUM_SAMPLES)
cz_buf = deque(maxlen=NUM_SAMPLES)
c4_buf = deque(maxlen=NUM_SAMPLES)

fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
fig.suptitle("Live EEG — 8-30 Hz Bandpass  |  STM32WB55 / ADS1294", fontsize=12)

lines = []
channel_names = ["C3", "Cz", "C4"]
colors = ['tab:blue', 'tab:orange', 'tab:green']

for ax, label, color in zip(axes, channel_names, colors):
    line, = ax.plot([], [], color=color, linewidth=0.8)
    lines.append(line)
    ax.set_ylabel(label)
    ax.set_ylim(-YRANGE, YRANGE)
    ax.axhline(0, color='gray', linewidth=0.5, linestyle='--')
    ax.grid(True, alpha=0.3)

axes[2].set_xlabel("Frame Count")

# Status boxes for each channel
status_boxes = []
for i, (ax, color) in enumerate(zip(axes, colors)):
    txt = ax.text(0.01, 0.92, "waiting...", transform=ax.transAxes,
                  fontsize=9, va='top', family='monospace',
                  bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))
    status_boxes.append(txt)

plt.tight_layout(rect=[0, 0, 1, 0.97])

line_c3, line_cz, line_c4 = lines
bufs = [c3_buf, cz_buf, c4_buf]


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

            if parts[0] == "D" and len(parts) == 7:
                x_buf.append(int(parts[1]))
                c3_buf.append(int(parts[3]))
                cz_buf.append(int(parts[4]))
                c4_buf.append(int(parts[5]))

            elif parts[0] == "I":
                print("[STM]", ",".join(parts[1:]))

        except ValueError:
            continue
        except Exception as e:
            print("Read error:", e)
            break

    if len(x_buf) == 0:
        return lines

    n = min(len(x_buf), len(c3_buf), len(cz_buf), len(c4_buf))
    if n == 0:
        return lines

    x = list(x_buf)[-n:]

    for line_obj, buf, status_box in zip(lines, bufs, status_boxes):
        filtered = bandpass_filter(list(buf)[-n:])
        line_obj.set_data(x, filtered)

        color, label = contact_quality(buf)
        status_box.set_text(label)
        status_box.get_bbox_patch().set_facecolor(
            {'green': '#90EE90', 'orange': '#FFD580',
             'red': '#FF9999', 'gray': 'wheat'}[color]
        )

    for ax in axes:
        ax.set_xlim(x[0], x[-1])

    return lines


ani = FuncAnimation(fig, update, interval=UPDATE_MS, blit=False, cache_frame_data=False)

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