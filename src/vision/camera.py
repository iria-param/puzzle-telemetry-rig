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
        self._stop_requested = threading.Event()
        self._lock = threading.Lock()
        self._jpeg = None
        self._sequence = 0
        self._state = "stopped"
        self._message = "Camera capture is stopped"
        self._retry_s = 2.0

    def start(self) -> None:
        """Start capture without making dashboard startup depend on the camera."""
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            self._state = "starting"
            self._message = f"Waiting for camera index {self.index}"
        self._stop_requested.clear()
        self._thread = threading.Thread(target=self._capture_frames, name="camera-capture", daemon=True)
        self._thread.start()

    def _open_capture(self):
        capture = cv2.VideoCapture(self.index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        capture.set(cv2.CAP_PROP_FPS, self.fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not capture.isOpened():
            capture.release()
            return None
        return capture

    def _capture_frames(self) -> None:
        while not self._stop_requested.is_set():
            if self._capture is None:
                try:
                    self._capture = self._open_capture()
                except Exception as exc:  # OpenCV/backend errors must not stop hardware telemetry.
                    with self._lock:
                        self._state = "unavailable"
                        self._message = f"Camera open failed: {exc}"
                    self._stop_requested.wait(self._retry_s)
                    continue
                if self._capture is None:
                    with self._lock:
                        self._state = "unavailable"
                        self._message = f"Camera index {self.index} is unavailable; retrying"
                        self._jpeg = None
                    self._stop_requested.wait(self._retry_s)
                    continue

            ok, frame = self._capture.read()
            if not ok:
                self._capture.release()
                self._capture = None
                with self._lock:
                    self._state = "unavailable"
                    self._message = "Camera stopped returning frames; retrying"
                    self._jpeg = None
                self._stop_requested.wait(0.2)
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
                    self._state = "connected"
                    self._message = "Live camera view"

    def latest_jpeg(self) -> tuple[bytes | None, int]:
        """Return the latest in-memory JPEG and its monotonically increasing id."""
        with self._lock:
            return self._jpeg, self._sequence

    def status(self) -> dict:
        """Return camera availability without exposing or storing a frame."""
        with self._lock:
            return {"state": self._state, "message": self._message, "index": self.index}

    def stop(self) -> None:
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        with self._lock:
            self._jpeg = None
            self._state = "stopped"
            self._message = "Camera capture is stopped"
