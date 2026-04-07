import os
import re
import numpy as np
import pandas as pd


FS = 250  # sampling frequency
CHANNELS = ["C3", "Cz", "C4"]
TMIN_SEC = 0.5
TMAX_SEC = 3.5

TMIN_SAMPLES = int(TMIN_SEC * FS)
TMAX_SAMPLES = int(TMAX_SEC * FS)
TRIAL_LEN = TMAX_SAMPLES - TMIN_SAMPLES

TMIN_SAMPLES = int(TMIN_SEC * FS)
TMAX_SAMPLES = int(TMAX_SEC * FS)
TRIAL_LEN = TMAX_SAMPLES - TMIN_SAMPLES

LABEL_MAP = {
    "IMAGERY_LEFT": 0,
    "IMAGERY_RIGHT": 1,
}

def load_session(samples_path, events_path):
    samples = pd.read_csv(samples_path)
    events = pd.read_csv(events_path)

    samples = samples.sort_values("sample_idx").reset_index(drop=True)
    events = events.sort_values("sample_idx").reset_index(drop=True)

    return samples, events

def check_frame_continuity(samples, user_id, session_id):
    indices = samples["sample_idx"].to_numpy()
    gaps = np.diff(indices)
    dropped = np.sum(gaps != 1)
    if dropped > 0:
        print(f"  WARNING {user_id} {session_id}: {dropped} frame gaps, max gap={gaps.max()}")
    else:
        print(f"  OK {user_id} {session_id}: no frame gaps")
    return dropped

def extract_trials(samples, events, user_id, session_id):
    X = []
    y = []
    meta_rows = []
    
    imagery_events = events[events["event_name"].isin(LABEL_MAP.keys())].copy()
    
    for _, ev in imagery_events.iterrows():
        start_idx = int(ev["sample_idx"]) + TMIN_SAMPLES
        end_idx = int(ev["sample_idx"]) + TMAX_SAMPLES

        trial_df = samples[
            (samples["sample_idx"] >= start_idx) &
            (samples["sample_idx"] < end_idx)
        ]

        if len(trial_df) != TRIAL_LEN:
            print(f"Skipping {user_id} {session_id} trial {ev['trial_num']} due to wrong length: {len(trial_df)}")
            continue

        expected = np.arange(start_idx, end_idx)
        actual = trial_df["sample_idx"].to_numpy()

        if not np.array_equal(actual, expected):
            print(f"Skipping {user_id} {session_id} trial {ev['trial_num']} due to missing sample indices")
            continue

        x_trial = trial_df[CHANNELS].to_numpy(dtype=np.float64)
        label = LABEL_MAP[ev["event_name"]]

        X.append(x_trial)
        y.append(label)

        meta_rows.append({
            "user_id": user_id,
            "session_id": session_id,
            "trial_num": int(ev["trial_num"]),
            "event_name": ev["event_name"],
            "label": label,
            "sample_idx": int(ev["sample_idx"]),
            "timestamp_ms": int(ev["timestamp_ms"]),
        })

    return X, y, meta_rows

def find_session_pairs(data_root):
    """
    Looks inside:
        trails_data/
            test_user1/
            test_user2/
    and finds matching:
        mi_sessionXX_samples.csv
        mi_sessionXX_events.csv
    """
    session_pairs = []

    for user_id in os.listdir(data_root):
        user_dir = os.path.join(data_root, user_id)

        if not os.path.isdir(user_dir):
            continue

        files = os.listdir(user_dir)

        sample_files = [f for f in files if f.endswith("_samples.csv")]

        for sample_file in sample_files:
            events_file = sample_file.replace("_samples.csv", "_events.csv")

            sample_path = os.path.join(user_dir, sample_file)
            events_path = os.path.join(user_dir, events_file)

            if not os.path.exists(events_path):
                print(f"Missing matching events file for {sample_path}")
                continue

            session_name = sample_file.replace("mi_", "").replace("_samples.csv", "")

            session_pairs.append({
                "user_id": user_id,
                "session_id": session_name,
                "samples_path": sample_path,
                "events_path": events_path,
            })

    return session_pairs


def build_dataset(data_root):
    all_X = []
    all_y = []
    all_meta_rows = []

    session_pairs = find_session_pairs(data_root)

    if len(session_pairs) == 0:
        raise ValueError("No session pairs found.")

    for pair in session_pairs:
        user_id = pair["user_id"]
        session_id = pair["session_id"]
        samples_path = pair["samples_path"]
        events_path = pair["events_path"]

        print(f"Processing user={user_id}, session={session_id}")
        print(f"  samples: {samples_path}")
        print(f"  events : {events_path}")

        samples, events = load_session(samples_path, events_path)
        check_frame_continuity(samples, user_id, session_id)
        X_list, y_list, meta_rows = extract_trials(samples, events, user_id, session_id)

        all_X.extend(X_list)
        all_y.extend(y_list)
        all_meta_rows.extend(meta_rows)

    if len(all_X) == 0:
        raise ValueError("No valid trials extracted.")

    X = np.array(all_X, dtype=np.float64)   # (n_trials, n_samples, n_channels)
    y = np.array(all_y, dtype=np.int64)
    meta = pd.DataFrame(all_meta_rows)

    return X, y, meta


if __name__ == "__main__":
    PROJECT_DIR = r"C:\Users\nikhi\Desktop\ECE395\mi_training"
    DATA_ROOT = os.path.join(PROJECT_DIR, "trails_data")
    OUT_DIR = os.path.join(PROJECT_DIR, "processed")

    os.makedirs(OUT_DIR, exist_ok=True)

    X, y, meta = build_dataset(DATA_ROOT)

    np.save(os.path.join(OUT_DIR, "X.npy"), X)
    np.save(os.path.join(OUT_DIR, "y.npy"), y)
    meta.to_csv(os.path.join(OUT_DIR, "metadata.csv"), index=False)

    print("\nSaved:")
    print("X shape:", X.shape)
    print("y shape:", y.shape)
    print(meta.head())