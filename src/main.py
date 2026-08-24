"""LEGACY STUB — this is NOT the rig's entry point any more.

The rig runs entirely from the live dashboard, which serves the webcam +
sensor page AND runs the whole session state machine (camera-verified
start/stop via the limit switch, five-minute safety timeout, CSV logging):

    cd ~/phase_1 && source ~/puzzle-venv/bin/activate
    python src/tools/live_dashboard.py

This file is kept only so old instructions fail loudly instead of silently.
The rev-1 button-based scaffold it used to contain was retired on
24 Aug 2026 (see CLAUDE.md §4 for the current state machine).
"""

import sys

if __name__ == "__main__":
    print(__doc__)
    sys.exit(1)
