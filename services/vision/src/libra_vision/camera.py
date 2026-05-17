"""Camera capture loop.

Thin cv2.VideoCapture wrapper that yields BGR frames. Handles the common
"device went away" case by raising CameraError with a clear message —
callers decide whether to retry, exit, or alert.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    pass


@contextmanager
def open_camera(
    source: int | str,
    *,
    width: int = 640,
    height: int = 480,
) -> Iterator["CameraStream"]:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise CameraError(f"Could not open camera source: {source!r}")
    # Hint dimensions; the driver may ignore them — that's fine.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    logger.info("vision: camera %r opened (%dx%d)", source, width, height)
    try:
        yield CameraStream(cap)
    finally:
        cap.release()
        logger.info("vision: camera released")


class CameraStream:
    def __init__(self, cap: cv2.VideoCapture) -> None:
        self._cap = cap
        self._frame_id = 0

    def frames(self, *, stride: int = 1) -> Iterator[tuple[int, np.ndarray]]:
        """Yield (frame_id, frame) tuples. `stride` drops every N-1 frames."""
        consecutive_failures = 0
        while True:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    raise CameraError("camera read failed 30 times in a row")
                # Brief pause then keep trying. USB cams hiccup.
                time.sleep(0.05)
                continue
            consecutive_failures = 0
            self._frame_id += 1
            if self._frame_id % stride != 0:
                continue
            yield self._frame_id, frame
