import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vision.camera import CameraStream


class CameraStreamTests(unittest.TestCase):
    @patch("vision.camera.cv2.VideoCapture")
    def test_missing_camera_does_not_prevent_startup(self, video_capture):
        missing = Mock()
        missing.isOpened.return_value = False
        video_capture.return_value = missing
        camera = CameraStream(index=0, width=640, height=480, fps=5, jpeg_quality=80)
        camera._retry_s = 0.01

        camera.start()
        deadline = time.monotonic() + 0.5
        while camera.status()["state"] == "starting" and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(camera.status()["state"], "unavailable")
        self.assertEqual(camera.latest_jpeg(), (None, 0))
        camera.stop()
        self.assertEqual(camera.status()["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
