import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import welch
import serial
import csv
import time
import os
import threading

PORT = "COM5"
BAUD = 460800
RECORD_SEC = 30
FS = 250

PROJECT_DIR = r"C:\Users\nikhi\Desktop\ECE395\mi_training"
OUT_FILE = os.path.join(PROJECT_DIR, "noise_test.csv")

stop_reader = False
rows = []

def serial_reader(ser):
    global stop_reader
    while not stop_reader:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
        except:
            break
        if not line:
            continue
        parts = line.split(",")
        if parts[0] == "D" and len(parts) == 7:
            rows.append(parts[1:])
        elif parts[0] == "I":
            print("[STM]", ",".join(parts[1:]))

def main():
    global stop_reader

    print("Connecting...")
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    t = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
    t.start()

    ser.write(b"START\n")
    ser.flush()
    print(f"Recording {RECORD_SEC}s — keep electrodes shorted or sit still...")

    time.sleep(RECORD_SEC)

    ser.write(b"STOP\n")
    ser.flush()
    time.sleep(0.5)
    stop_reader = True
    t.join(timeout=2.0)
    ser.close()

    # Save
    df = pd.DataFrame(rows, columns=["sample_idx", "timestamp_ms", "C3", "Cz", "C4", "CH4"])
    for ch in ["C3", "Cz", "C4", "CH4"]:
        df[ch] = pd.to_numeric(df[ch], errors="coerce")
    df.to_csv(OUT_FILE, index=False)
    print(f"Saved {len(df)} samples to {OUT_FILE}")

    # --- Analysis ---
    LSB_TO_UV = (4.5 / (24 * 2**23)) * 1e6

    print("\n--- Noise Floor (RMS) ---")
    for ch in ["C3", "Cz", "C4"]:
        data = df[ch].dropna().to_numpy(dtype=float) * LSB_TO_UV
        rms = np.sqrt(np.mean(data**2))
        print(f"  {ch}: {rms:.3f} µV RMS")

    print("\n--- Power Spectral Density ---")
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for ax, ch in zip(axes, ["C3", "Cz", "C4"]):
        data = df[ch].dropna().to_numpy(dtype=float) * LSB_TO_UV
        f, pxx = welch(data, fs=FS, nperseg=512)
        ax.semilogy(f, pxx)
        ax.set_ylabel(f"{ch}\n(µV²/Hz)")
        ax.set_title(f"{ch} PSD")
        ax.axvline(50, color='r', linestyle='--', alpha=0.5, label='50Hz')
        ax.legend()
    axes[-1].set_xlabel("Frequency (Hz)")
    plt.tight_layout()
    plt.savefig(os.path.join(PROJECT_DIR, "noise_test_psd.png"))
    plt.show()
    print("PSD plot saved.")

if __name__ == "__main__":
    main()