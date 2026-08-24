"""Threaded USB-camera capture for the local live dashboard.

Frames remain in memory only. This module never writes video or image files.
"""

import threading
import time

import cv2


class CameraStream:
    """Capture the most recent webcam frame and encode it as JPEG."""

    def __init__(self, index: int, width: int, height: int, fps: int, jpeg_quality: int):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._capture = None
        self._thread = None
        self._running = threading.Event()
        self._lock = threading.Lock()
        self._jpeg = None
        self._sequence = 0

    def start(self) -> None:
        """Open the camera and start background capture."""
        capture = cv2.VideoCapture(self.index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        capture.set(cv2.CAP_PROP_FPS, self.fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"could not open camera index {self.index}")

        self._capture = capture
        self._running.set()
        self._thread = threading.Thread(target=self._capture_frames, name="camera-capture", daemon=True)
        self._thread.start()

    def _capture_frames(self) -> None:
        while self._running.is_set():
            ok, frame = self._capture.read()
            if not ok:
                time.sleep(0.1)
                continue
            ok, encoded = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
            )
            if ok:
                with self._lock:
                    self._jpeg = encoded.tobytes()
                    self._sequence += 1

    def latest_jpeg(self) -> tuple[bytes | None, int]:
        """Return the latest in-memory JPEG and its monotonically increasing id."""
        with self._lock:
            return self._jpeg, self._sequence

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._capture is not None:
            self._capture.release()
