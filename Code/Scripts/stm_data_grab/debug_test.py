import serial
import time

PORT = "COM5"
BAUD = 460800

ser = serial.Serial(PORT, BAUD, timeout=0.5)
ser.reset_input_buffer()
ser.reset_output_buffer()

print("Waiting for STM32... press RST button on Nucleo")
while True:
    line = ser.readline().decode("utf-8", errors="ignore").strip()
    if not line:
        continue
    print(f"[BOOT] {line}")
    if "READY" in line:
        break

print("Sending START...")
ser.write(b"START\n")
ser.flush()

print("Listening for 30 seconds...")
print("Format: frame, timestamp_ms, C3, Cz, C4, CH4")
print("-" * 60)

t_end = time.time() + 30.0

while time.time() < t_end:
    line = ser.readline().decode("utf-8", errors="ignore").strip()
    if not line:
        continue
    if line.startswith("I,"):
        print(f"[STM] {line[2:]}")
    elif line.startswith("D,"):
        parts = line.split(",")
        if len(parts) == 7:
            frame = parts[1]
            ts    = parts[2]
            c3    = parts[3]
            cz    = parts[4]
            c4    = parts[5]
            ch4   = parts[6]
            print(f"frame={frame:>8}  ts={ts:>8}ms  C3={c3:>12}  Cz={cz:>12}  C4={c4:>12}  CH4={ch4:>12}")
    else:
        print(f"[RAW] {line}")

ser.write(b"STOP\n")
ser.flush()
ser.close()
print("Done.")