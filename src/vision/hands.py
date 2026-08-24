"""Milestone C — hand-presence tracking (NOT implemented yet).

Plan (CLAUDE.md §7 stack): OpenCV capture from /dev/video0 at 640x480 ~5 fps,
MediaPipe Hand Landmarker counts frames with >=1 hand visible. Feeds the
hand_frames_pct and frames_total columns of the session CSV.
"""
