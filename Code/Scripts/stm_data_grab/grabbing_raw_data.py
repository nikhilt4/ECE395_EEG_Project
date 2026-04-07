import serial
import csv
import time
import os

PORT = "COM5"   # change this
BAUD = 460800
OUTFILE = r"C:\Users\nikhi\Desktop\ECE395\trails_data\test_user1\mi_session01.csv"

os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)

with open(OUTFILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["sample_idx", "timestamp_ms", "C3", "Cz", "C4", "CH4"])

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            parts = line.split(",")
            if len(parts) != 6:
                print("Skipping:", line)
                continue

            writer.writerow(parts)
            print(parts)

    except KeyboardInterrupt:
        pass

ser.close()