import serial
import csv
import time
import os
import threading
import random
import winsound

PORT = "COM5"
BAUD = 460800

PROJECT_DIR = r"C:\Users\nikhi\Desktop\ECE395\mi_training"
DATA_ROOT = os.path.join(PROJECT_DIR, "trails_data")

while True:
    USER_ID = input("Enter user ID (e.g. user01): ").strip()
    SESSION_ID = input("Enter session ID (e.g. session01): ").strip()
    BASE_DIR = os.path.join(DATA_ROOT, USER_ID)
    SAMPLES_FILE = os.path.join(BASE_DIR, f"mi_{SESSION_ID}_samples.csv")
    EVENTS_FILE  = os.path.join(BASE_DIR, f"mi_{SESSION_ID}_events.csv")

    if os.path.exists(SAMPLES_FILE):
        print(f"WARNING: session '{SESSION_ID}' for user '{USER_ID}' already exists. Choose different IDs.")
    else:
        break

os.makedirs(BASE_DIR, exist_ok=True)
print(f"OK: saving to {BASE_DIR}")

# Trial timing in seconds
PREPARE_SEC = 4.0
CUE_SEC = 1.0
IMAGERY_SEC = 4.0
REST_SEC = 4.0

# Event codes
EVENT_PREPARE      = 1
EVENT_CUE_LEFT     = 2
EVENT_CUE_RIGHT    = 3
EVENT_IMAGERY_LEFT = 4
EVENT_IMAGERY_RIGHT= 5
EVENT_REST         = 6

# Build trial list: 10 left, 10 right
trial_labels = ["LEFT"] * 10 + ["RIGHT"] * 10
random.shuffle(trial_labels)

stop_reader = False
reader_thread = None
csv_lock = threading.Lock()


def send_cmd(ser, cmd: str):
    ser.write((cmd + "\n").encode("utf-8"))
    ser.flush()
    print(f">>> {cmd}")


def beep_prepare():
    winsound.Beep(440, 150)
    
def beep_cue():
    winsound.Beep(880, 300)
    
def beep_rest():
    winsound.Beep(300, 500)


def serial_reader(ser, samples_writer, events_writer, samples_f, events_f):
    global stop_reader, expected_idx, gap_count

    while not stop_reader:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
        except serial.SerialException as e:
            print("Serial error:", e)
            break

        if not line:
            continue

        parts = line.split(",")

        with csv_lock:
            # if parts[0] == "D" and len(parts) == 7:
            #     # D,sample_idx,timestamp_ms,C3,Cz,C4,CH4
            #     samples_writer.writerow(parts[1:])
            #     samples_f.flush()
            if parts[0] == "D" and len(parts) == 7:
                sample_idx = int(parts[1])
                if expected_idx > 0 and sample_idx != expected_idx:
                    gap_count += 1
                    print(f"[GAP] sample={sample_idx}, gap={sample_idx - expected_idx}, total_gaps={gap_count}")
                expected_idx = sample_idx + 1
                samples_writer.writerow(parts[1:])
                samples_f.flush()

            elif parts[0] == "E" and len(parts) >= 6:
                # E,sample_idx,timestamp_ms,trial_num,event_code,event_name
                event_name = ",".join(parts[5:])  # in case event name ever has commas
                events_writer.writerow([parts[1], parts[2], parts[3], parts[4], event_name])
                events_f.flush()

            elif parts[0] == "I":
                print("[STM]", ",".join(parts[1:]))

            else:
                print("Skipping:", line)


def do_phase(ser, trial_num, event_code, event_name, duration, display_text=None, beep_fn=None):
    send_cmd(ser, f"MARK,{trial_num},{event_code},{event_name}")
    if display_text is not None:
        print(f"\n=== {display_text} ===")
    if beep_fn is not None:
        beep_fn()
    t_end = time.time() + duration
    while time.time() < t_end:
        time.sleep(0.05)


def main():
    global stop_reader, reader_thread

    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    time.sleep(2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    with open(SAMPLES_FILE, "w", newline="") as samples_f, open(EVENTS_FILE, "w", newline="") as events_f:
        samples_writer = csv.writer(samples_f)
        events_writer = csv.writer(events_f)

        samples_writer.writerow(["sample_idx", "timestamp_ms", "C3", "Cz", "C4", "CH4"])
        events_writer.writerow(["sample_idx", "timestamp_ms", "trial_num", "event_code", "event_name"])

        stop_reader = False
        reader_thread = threading.Thread(
            target=serial_reader,
            args=(ser, samples_writer, events_writer, samples_f, events_f),
            daemon=True
        )
        reader_thread.start()

        try:
            print("Starting run...")
            send_cmd(ser, "START")
            time.sleep(1.0)

            for i, label in enumerate(trial_labels, start=1):
                print(f"\n######## Trial {i} / {len(trial_labels)} : {label} ########")

                do_phase(ser, i, EVENT_PREPARE, "PREPARE", PREPARE_SEC, beep_fn=beep_prepare)

                if label == "LEFT":
                    do_phase(ser, i, EVENT_CUE_LEFT, "CUE_LEFT", CUE_SEC, "LEFT CUE", beep_fn=beep_cue)
                    do_phase(ser, i, EVENT_IMAGERY_LEFT, "IMAGERY_LEFT", IMAGERY_SEC, "IMAGINE LEFT HAND")
                else:
                    do_phase(ser, i, EVENT_CUE_RIGHT, "CUE_RIGHT", CUE_SEC, "RIGHT CUE", beep_fn=beep_cue)
                    do_phase(ser, i, EVENT_IMAGERY_RIGHT, "IMAGERY_RIGHT", IMAGERY_SEC, "IMAGINE RIGHT HAND")

                do_phase(ser, i, EVENT_REST, "REST", REST_SEC, "REST", beep_fn=beep_rest)

            print("\nRun complete. Sending STOP...")
            send_cmd(ser, "STOP")
            time.sleep(1.0)

        except KeyboardInterrupt:
            print("\nInterrupted by user. Sending STOP...")
            send_cmd(ser, "STOP")
            time.sleep(1.0)

        finally:
            stop_reader = True
            reader_thread.join(timeout=2.0)
            ser.close()

    print("Saved:")
    print(SAMPLES_FILE)
    print(EVENTS_FILE)


if __name__ == "__main__":
    main()