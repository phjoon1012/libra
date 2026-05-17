"""YOLO inference wrapper.

Wraps Ultralytics so the rest of the app sees a tiny `detect(frame) ->
list[Detection]` surface. Lets us swap to ONNX/TensorRT later without
touching the camera/policy/publisher code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels


class YoloDetector:
    def __init__(
        self,
        model_path: str,
        *,
        confidence: float = 0.45,
        device: str = "",
        class_filter: tuple[str, ...] = (),
    ) -> None:
        # Imported lazily so `--help` etc. don't pay the torch import cost.
        from ultralytics import YOLO

        self._model = YOLO(model_path)
        self._confidence = confidence
        self._device = self._resolve_device(device)
        self._class_filter = set(class_filter)

        # Map filter labels -> class ids once. Anything we can't resolve we
        # log a warning so misconfiguration is visible.
        names = getattr(self._model, "names", {}) or {}
        name_to_id: dict[str, int] = {
            (v if isinstance(v, str) else str(v)): int(k)
            for k, v in (names.items() if isinstance(names, dict) else enumerate(names))
        }
        self._names = name_to_id
        self._allowed_ids: list[int] | None = None
        if self._class_filter:
            allowed = [
                name_to_id[c] for c in self._class_filter if c in name_to_id
            ]
            missing = [c for c in self._class_filter if c not in name_to_id]
            if missing:
                logger.warning(
                    "vision: dropping unknown class filter entries: %s", missing
                )
            self._allowed_ids = allowed or None

        logger.info(
            "vision: detector ready (model=%s device=%s conf>=%.2f filter=%s)",
            model_path,
            self._device,
            confidence,
            sorted(self._class_filter) or "all",
        )

    @staticmethod
    def _resolve_device(requested: str) -> str:
        if requested:
            return requested
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                return "cuda:0"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                return "mps"
        except Exception:  # pragma: no cover — fallback in any env
            pass
        return "cpu"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run inference on a single BGR frame, return filtered detections."""
        kwargs: dict[str, Any] = {
            "conf": self._confidence,
            "verbose": False,
            "device": self._device,
        }
        if self._allowed_ids is not None:
            kwargs["classes"] = self._allowed_ids

        results = self._model.predict(frame, **kwargs)
        if not results:
            return []
        r = results[0]
        boxes = getattr(r, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        xyxy = boxes.xyxy.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy().astype(float)
        clss = boxes.cls.cpu().numpy().astype(int)

        out: list[Detection] = []
        for (x1, y1, x2, y2), conf, cid in zip(xyxy, confs, clss):
            label = self._label_for(int(cid))
            out.append(
                Detection(
                    label=label,
                    confidence=float(conf),
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                )
            )
        return out

    def _label_for(self, cid: int) -> str:
        # Reverse map id -> label for output.
        for name, idx in self._names.items():
            if idx == cid:
                return name
        return str(cid)
