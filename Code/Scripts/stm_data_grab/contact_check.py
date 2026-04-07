import serial
import time

PORT = "COM5"
BAUD = 460800
POLL_SEC = 1.0

def send_cmd(ser, cmd):
    ser.write((cmd + "\n").encode("utf-8"))
    ser.flush()
    print(f">>> {cmd}")

def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.2)
    time.sleep(2)

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    try:
        print("Entering contact-check mode...")
        send_cmd(ser, "CONTACT_ON")
        time.sleep(0.5)

        print("Polling contact status. Press Ctrl+C to stop.\n")

        while True:
            send_cmd(ser, "CONTACT_STATUS")

            t_end = time.time() + POLL_SEC
            while time.time() < t_end:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                # Firmware sends info as I,...
                if line.startswith("I,"):
                    print(line)
                else:
                    print("RX:", line)

    except KeyboardInterrupt:
        print("\nStopping contact check...")

    finally:
        try:
            send_cmd(ser, "CONTACT_OFF")
            time.sleep(0.2)
        except Exception:
            pass

        ser.close()
        print("Serial port closed.")

if __name__ == "__main__":
    main()