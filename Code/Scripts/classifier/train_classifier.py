import os
import json
import joblib
import numpy as np
import pandas as pd

from scipy.signal import butter, lfilter
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
from sklearn.model_selection import GroupShuffleSplit, GroupKFold, cross_val_score
from sklearn.pipeline import Pipeline
from mne.decoding import CSP

FS = 250
LOWCUT = 8.0
HIGHCUT = 30.0
CSP_COMPONENTS = 2

PROJECT_DIR = r"C:\Users\nikhi\Desktop\ECE395\mi_training"
PROCESSED_DIR = os.path.join(PROJECT_DIR, "processed")
MODEL_DIR = os.path.join(PROJECT_DIR, "models")


def load_data():
    X = np.load(os.path.join(PROCESSED_DIR, "X.npy"))
    y = np.load(os.path.join(PROCESSED_DIR, "y.npy"))
    meta = pd.read_csv(os.path.join(PROCESSED_DIR, "metadata.csv"))
    return X, y, meta


def remove_dc(X):
    # X shape: (n_trials, n_samples, n_channels)
    return X - X.mean(axis=1, keepdims=True)


def bandpass_trials(X, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT, order=4):
    """
    Filter each trial with lfilter — matches STM32 real-time behavior exactly.
    Note: filter each session continuously rather than per-trial for best results,
    but per-trial is used here to match the saved epoch structure.
    """
    nyq = 0.5 * fs
    b, a = butter(order, [lowcut / nyq, highcut / nyq], btype='band')
    Xf = np.empty_like(X, dtype=np.float64)
    for i in range(X.shape[0]):
        Xf[i] = lfilter(b, a, X[i], axis=0)
    return Xf, b, a


def split_by_subject(X, y, meta):
    """
    Hold out subjects entirely — honest cross-subject generalization estimate.
    This matches deployment: new user has never been in training set.
    """
    groups = meta["user_id"].to_numpy()

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.25,  # ~10 subjects held out from 40
        random_state=42
    )

    train_idx, test_idx = next(splitter.split(X, y, groups=groups))

    return X[train_idx], X[test_idx], y[train_idx], y[test_idx], groups[train_idx]


def cross_validate_by_subject(X, y, meta):
    """
    5-fold cross-validation holding out subjects per fold.
    Gives honest estimate of accuracy on unseen subjects.
    """
    groups = meta["user_id"].to_numpy()

    pipeline = Pipeline([
        ('csp', CSP(n_components=CSP_COMPONENTS, reg='ledoit_wolf',
                    log=True, norm_trace=False)),
        ('lda', LinearDiscriminantAnalysis(solver='lsqr', shrinkage='auto'))
    ])

    cv = GroupKFold(n_splits=14)
    scores = cross_val_score(pipeline, X, y, groups=groups, cv=cv)

    print(f"\nCross-subject CV accuracy: {scores.mean():.3f} ± {scores.std():.3f}")
    print(f"Per-fold: {np.round(scores, 3)}")
    return scores


def save_model(csp, clf, band_b, band_a):
    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(
        {"csp": csp, "clf": clf, "band_b": band_b, "band_a": band_a},
        os.path.join(MODEL_DIR, "mi_csp_lda.joblib")
    )

    params = {
        "fs": FS,
        "lowcut": LOWCUT,
        "highcut": HIGHCUT,
        "band_b": band_b.tolist(),
        "band_a": band_a.tolist(),
        "csp_filters": csp.filters_[:CSP_COMPONENTS].tolist(),
        "lda_coef": clf.coef_.tolist(),
        "lda_intercept": clf.intercept_.tolist(),
        "classes": clf.classes_.tolist(),
    }

    with open(os.path.join(MODEL_DIR, "mi_params.json"), "w") as f:
        json.dump(params, f, indent=2)


def main():
    X, y, meta = load_data()

    print("Loaded X shape:", X.shape)
    print("Loaded y shape:", y.shape)
    print("Subjects:", meta["user_id"].nunique())

    # Preprocess
    X = remove_dc(X)
    X, band_b, band_a = bandpass_trials(X)

    # CSP wants: (n_trials, n_channels, n_times)
    X = np.transpose(X, (0, 2, 1))

    # Cross-validation first — honest accuracy estimate before final model
    cross_validate_by_subject(X, y, meta)

    # Train/test split by subject
    X_train, X_test, y_train, y_test, _ = split_by_subject(X, y, meta)

    print(f"\nTrain trials: {len(X_train)}, Test trials: {len(X_test)}")

    # Train CSP with regularization
    csp = CSP(n_components=CSP_COMPONENTS, reg='ledoit_wolf',
              log=True, norm_trace=False)
    X_train_csp = csp.fit_transform(X_train, y_train)
    X_test_csp = csp.transform(X_test)

    # Train LDA with shrinkage for robustness
    clf = LinearDiscriminantAnalysis(solver='lsqr', shrinkage='auto')
    clf.fit(X_train_csp, y_train)

    # Evaluate
    y_pred = clf.predict(X_test_csp)

    print("\nHeld-out subject accuracy:", accuracy_score(y_test, y_pred))
    print("\nConfusion matrix:")
    print(confusion_matrix(y_test, y_pred))
    print("\nClassification report:")
    print(classification_report(y_test, y_pred, target_names=["LEFT", "RIGHT"]))

    # Save
    save_model(csp, clf, band_b, band_a)
    print("\nSaved model in:", MODEL_DIR)


if __name__ == "__main__":
    main()