import serial
import time

PORT = "COM5"
BAUD = 460800

def wait_for_stm32(port, baud, timeout_per_attempt=5.0):
    print(f"Waiting for STM32 on {port} at {baud} baud...")

    while True:
        try:
            ser = serial.Serial(port, baud, timeout=0.1)
            print("Port opened. Waiting for STM32 boot messages...")

            t_start = time.time()
            while (time.time() - t_start) < timeout_per_attempt:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                print(f"[BOOT] {line}")

                if line == "I,READY" or "READY" in line:
                    print("\nSTM32 is ready and ADS1299 init likely succeeded.\n")
                    return ser

            print("No READY received within timeout, closing and retrying...")
            ser.close()
            time.sleep(1)

        except serial.SerialException as e:
            print(f"Cannot open port ({e}) — retrying in 2s...")
            time.sleep(2)

def drain_info(ser, duration=3.0):
    print(f"Listening for {duration}s of post-boot messages...")
    t_end = time.time() + duration
    while time.time() < t_end:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"[POST-BOOT] {line}")
    print("\nDone listening.")

def main():
    ser = wait_for_stm32(PORT, BAUD)
    drain_info(ser, duration=3.0)
    ser.close()
    print("Port closed. Done.")

if __name__ == "__main__":
    main()