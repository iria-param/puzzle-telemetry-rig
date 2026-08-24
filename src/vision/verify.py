"""Position- and rotation-independent T-puzzle completion check.

The checker extracts the largest tan cardboard component and compares its
contour and area with the solved T. It does not identify individual pieces.
"""

import threading
import time
from pathlib import Path

import cv2
import numpy as np


class CompletionVerifier:
    """Save a solved reference and compare current cardboard-shape masks to it."""

    def __init__(self, config: dict):
        self._reference_path = Path(config["reference_image"])
        self._mask_path = Path(config["reference_mask"])
        self._lower_hsv = np.array(config["hsv_lower"], dtype=np.uint8)
        self._upper_hsv = np.array(config["hsv_upper"], dtype=np.uint8)
        self._kernel_size = config["morphology_kernel"]
        self._min_component_pixels = config["min_component_pixels"]
        self._max_shape_score = config["max_shape_score"]
        self._min_area_ratio = config["min_area_ratio"]
        self._max_area_ratio = config["max_area_ratio"]
        self._lock = threading.Lock()
        self._reference_mask = self._load_reference_mask()
        self._last_result = {"state": "reference_ready" if self._reference_mask is not None else "reference_required"}

    def _load_reference_mask(self) -> np.ndarray | None:
        if not self._mask_path.exists():
            return None
        mask = cv2.imread(str(self._mask_path), cv2.IMREAD_GRAYSCALE)
        return mask if mask is not None else None

    def _decode(self, jpeg: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("could not decode the current camera frame")
        return image

    def _mask(self, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._lower_hsv, self._upper_hsv)
        kernel = np.ones((self._kernel_size, self._kernel_size), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    def _largest_component(self, mask: np.ndarray) -> tuple[np.ndarray, int]:
        """Return the largest connected cardboard component and its pixel area."""
        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if labels_count <= 1:
            raise ValueError("no cardboard component detected")
        largest_index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        pixels = int(stats[largest_index, cv2.CC_STAT_AREA])
        if pixels < self._min_component_pixels:
            raise ValueError("largest cardboard component is too small")
        return np.where(labels == largest_index, 255, 0).astype(np.uint8), pixels

    @staticmethod
    def _contour(component: np.ndarray) -> np.ndarray:
        contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError("could not find a cardboard contour")
        return max(contours, key=cv2.contourArea)

    def capture_reference(self, jpeg: bytes) -> dict:
        """Store a board-only solved-T reference and its segmentation mask."""
        image = self._decode(jpeg)
        mask = self._mask(image)
        _, pixels = self._largest_component(mask)

        self._reference_path.parent.mkdir(parents=True, exist_ok=True)
        self._mask_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(self._reference_path), image):
            raise OSError(f"could not write {self._reference_path}")
        if not cv2.imwrite(str(self._mask_path), mask):
            raise OSError(f"could not write {self._mask_path}")

        with self._lock:
            self._reference_mask = mask
            self._last_result = {
                "state": "reference_saved",
                "reference_component_pixels": pixels,
                "captured_at": time.strftime("%H:%M:%S"),
            }
            return self._last_result.copy()

    def check(self, jpeg: bytes) -> dict:
        """Return the current T-puzzle completion decision and interpretable scores."""
        with self._lock:
            reference = None if self._reference_mask is None else self._reference_mask.copy()
        if reference is None:
            result = {"state": "reference_required"}
        else:
            try:
                reference_component, reference_pixels = self._largest_component(reference)
                candidate_component, candidate_pixels = self._largest_component(self._mask(self._decode(jpeg)))
                shape_score = cv2.matchShapes(
                    self._contour(reference_component),
                    self._contour(candidate_component),
                    cv2.CONTOURS_MATCH_I1,
                    0.0,
                )
                area_ratio = candidate_pixels / reference_pixels
                complete = (
                    shape_score <= self._max_shape_score
                    and self._min_area_ratio <= area_ratio <= self._max_area_ratio
                )
                result = {
                    "state": "complete" if complete else "incomplete",
                    "shape_score": round(float(shape_score), 4),
                    "area_ratio": round(area_ratio, 3),
                    "checked_at": time.strftime("%H:%M:%S"),
                }
            except ValueError as exc:
                result = {"state": "incomplete", "message": str(exc), "checked_at": time.strftime("%H:%M:%S")}

        with self._lock:
            self._last_result = result
            return result.copy()

    def status(self) -> dict:
        with self._lock:
            return {
                "reference_saved": self._reference_mask is not None,
                "last_result": self._last_result.copy(),
            }
