import serial
import time
import os
from colorama import init, Fore, Style
init(autoreset=True)

PORT = "COM5"
BAUD = 460800
POLL_SEC = 0.75

def send_cmd(ser, cmd):
    ser.write((cmd + "\n").encode("utf-8"))
    ser.flush()

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def parse_contact_line(line):
    """
    Expected:
    I,CONTACT_CH,C3,OK,Cz,OFF,C4,OK,CH4,OK
    """
    parts = line.split(",")
    if len(parts) < 10:
        return None

    if parts[0] != "I" or parts[1] != "CONTACT_CH":
        return None

    status = {}
    try:
        for i in range(2, len(parts), 2):
            ch = parts[i]
            val = parts[i + 1]
            status[ch] = val
    except IndexError:
        return None

    return status

def parse_raw_line(line):
    """
    Expected:
    I,CONTACT_RAW,STATP=0x00,STATN=0x00
    """
    parts = line.split(",")
    if len(parts) < 4:
        return None

    if parts[0] != "I" or parts[1] != "CONTACT_RAW":
        return None

    return {
        "STATP": parts[2].replace("STATP=", ""),
        "STATN": parts[3].replace("STATN=", "")
    }

def status_note(val):
    if val == "OK":
        return "Good"
    if val == "OFF":
        return "Bad / reseat electrode"
    return "Unknown"

def color_status(val):
    if val == "OK":
        return Fore.GREEN + "OK" + Style.RESET_ALL
    if val == "OFF":
        return Fore.RED + "OFF" + Style.RESET_ALL
    if val == "WAIT":
        return Fore.YELLOW + "WAIT" + Style.RESET_ALL
    return val

def print_table(contact_status, raw_status, last_update):
    clear_screen()

    print("ADS1299 Electrode Contact Check")
    print("=" * 60)
    print(f"Last update: {last_update}")
    print()

    if raw_status is not None:
        print(f"Raw status bits: STATP={raw_status['STATP']}   STATN={raw_status['STATN']}")
        print()

    print("+---------+-----------------+-------------------------+")
    print("| Channel | Status          | Note                    |")
    print("+---------+-----------------+-------------------------+")

    for ch in ["C3", "Cz", "C4", "CH4"]:
        val = contact_status.get(ch, "WAIT")
        note = status_note(val) if val in ("OK", "OFF") else "Waiting for data"
        colored_val = color_status(val)
        print(f"| {ch:<7} | {colored_val:<15} | {note:<23} |")

    print("+---------+-----------------+-------------------------+")
    print()
    print("Ctrl+C to stop")
    print("Tip: part hair, add gel/paste, and press electrode onto scalp.")

def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.2)
    time.sleep(2)

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    contact_status = {
        "C3": "WAIT",
        "Cz": "WAIT",
        "C4": "WAIT",
        "CH4": "WAIT"
    }
    raw_status = None
    last_update = "No data yet"

    try:
        send_cmd(ser, "CONTACT_ON")
        time.sleep(0.3)

        while True:
            send_cmd(ser, "CONTACT_STATUS")

            t_end = time.time() + POLL_SEC
            while time.time() < t_end:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                parsed_contact = parse_contact_line(line)
                if parsed_contact is not None:
                    contact_status.update(parsed_contact)
                    last_update = time.strftime("%H:%M:%S")
                    continue

                parsed_raw = parse_raw_line(line)
                if parsed_raw is not None:
                    raw_status = parsed_raw
                    last_update = time.strftime("%H:%M:%S")
                    continue

            print_table(contact_status, raw_status, last_update)

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