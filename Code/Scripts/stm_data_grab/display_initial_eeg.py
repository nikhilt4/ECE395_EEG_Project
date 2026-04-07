import serial
import time
from collections import deque
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

PORT = "COM5"          # change this
BAUD = 460800          # match STM baud
NUM_SAMPLES = 500      # rolling window size on plot

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)

# Rolling buffers
x_buf  = deque(maxlen=NUM_SAMPLES)
c3_buf = deque(maxlen=NUM_SAMPLES)
cz_buf = deque(maxlen=NUM_SAMPLES)
c4_buf = deque(maxlen=NUM_SAMPLES)
ch4_buf = deque(maxlen=NUM_SAMPLES)

fig, ax = plt.subplots(figsize=(12, 6))
line_c3, = ax.plot([], [], label="C3")
line_cz, = ax.plot([], [], label="Cz")
line_c4, = ax.plot([], [], label="C4")
line_ch4, = ax.plot([], [], label="CH4")

ax.set_title("Live Raw EEG from UART")
ax.set_xlabel("Sample Index")
ax.set_ylabel("ADS1299 Raw Counts")
ax.legend()
ax.grid(True)

def update(frame):
    # Read multiple serial lines each animation frame
    for _ in range(30):
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            parts = line.split(",")
            if len(parts) != 6:
                continue

            sample_idx = int(parts[0])
            timestamp_ms = int(parts[1])   # currently unused, but kept for parsing
            c3 = int(parts[2])
            cz = int(parts[3])
            c4 = int(parts[4])
            ch4 = int(parts[5])

            x_buf.append(sample_idx)
            c3_buf.append(c3)
            cz_buf.append(cz)
            c4_buf.append(c4)
            ch4_buf.append(ch4)

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

    # Auto-scale y based on current data
    all_vals = list(c3_buf) + list(cz_buf) + list(c4_buf) + list(ch4_buf)
    y_min = min(all_vals)
    y_max = max(all_vals)

    if y_min == y_max:
        y_min -= 1
        y_max += 1

    margin = max(1000, int(0.1 * (y_max - y_min)))
    ax.set_ylim(y_min - margin, y_max + margin)

    return line_c3, line_cz, line_c4, line_ch4

ani = FuncAnimation(fig, update, interval=50, blit=False)

try:
    plt.show()
finally:
    ser.close()
    print("Serial port closed.")