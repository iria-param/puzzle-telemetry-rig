"""Session logging — one CSV row per puzzle session.

Schema must stay in sync with CLAUDE.md §5. Add a column there first,
then here, never the other way round.
"""

import csv
import os
from datetime import datetime

COLUMNS = [
    "session_id",
    "approach_ts",
    "start_ts",
    "stop_ts",
    "approach_to_start_s",
    "solve_time_s",
    "min_distance_cm",
    "hand_frames_pct",
    "frames_total",
    "verify_photo",
    "completed",   # pending / yes / no — manual label until vision/verify.py exists
    "notes",
]


class SessionLogger:
    def __init__(self, data_dir="data", csv_name="sessions.csv", images_dir="images"):
        self.data_dir = data_dir
        self.csv_path = os.path.join(data_dir, csv_name)
        self.images_dir = os.path.join(data_dir, images_dir)
        os.makedirs(self.images_dir, exist_ok=True)
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                csv.writer(f).writerow(COLUMNS)

    def next_session_id(self) -> str:
        """Sequential id like 2026-08-17_0042 (counter is global, not per-day)."""
        with open(self.csv_path) as f:
            n = sum(1 for _ in f) - 1  # minus header row
        return f"{datetime.now():%Y-%m-%d}_{n + 1:04d}"

    def append(self, row: dict) -> str:
        """Write one session row; missing columns are stored empty."""
        unknown = set(row) - set(COLUMNS)
        if unknown:
            raise ValueError(f"unknown session columns: {unknown}")
        full = {**{c: "" for c in COLUMNS}, **row}
        with open(self.csv_path, "a", newline="") as f:
            csv.writer(f).writerow([full[c] for c in COLUMNS])
        return full["session_id"]
