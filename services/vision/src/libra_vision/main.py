"""Entry point.

    libra-vision

Boots the camera, runs YOLO, applies the emission policy, publishes to
MQTT. Designed to run forever; Ctrl-C or SIGTERM triggers a clean
disconnect (publishes status="offline" before exiting).
"""

from __future__ import annotations

import logging
import signal
import socket
import sys
from types import FrameType
from typing import NoReturn

from .camera import CameraError, open_camera
from .config import VisionSettings, load_settings
from .detector import YoloDetector
from .policy import EmissionPolicy
from .publisher import MqttPublisher, PublisherConfig

logger = logging.getLogger("libra_vision")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
    )


def _make_publisher(settings: VisionSettings) -> MqttPublisher:
    client_id = f"libra-vision-{settings.source_id}-{socket.gethostname()}"[:64]
    cfg = PublisherConfig(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password,
        topic_detections=settings.topic_detections,
        topic_status=settings.topic_status,
        qos=settings.mqtt_qos,
        source_id=settings.source_id,
        client_id=client_id,
    )
    return MqttPublisher(cfg)


def run(settings: VisionSettings) -> None:
    detector = YoloDetector(
        settings.model,
        confidence=settings.confidence,
        device=settings.device,
        class_filter=settings.classes,
    )
    policy = EmissionPolicy(
        mode=settings.policy,
        heartbeat_seconds=settings.heartbeat_seconds,
    )
    publisher = _make_publisher(settings)
    publisher.start()

    stop_requested = False

    def _shutdown(signum: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        logger.info("vision: signal %d received, shutting down", signum)
        stop_requested = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        with open_camera(
            settings.camera_source,
            width=settings.frame_width,
            height=settings.frame_height,
        ) as cam:
            for frame_id, frame in cam.frames(stride=settings.frame_stride):
                if stop_requested:
                    break
                detections = detector.detect(frame)
                labels = [d.label for d in detections]
                decision = policy.evaluate(labels)
                if not decision.emit:
                    continue
                publisher.publish_detections(
                    frame_id=frame_id,
                    detections=detections,
                    reason=decision.reason,
                )
                logger.info(
                    "vision: emit (%s) frame=%d → %s",
                    decision.reason,
                    frame_id,
                    [d.label for d in detections] or "empty",
                )
    except CameraError as exc:
        logger.error("vision: camera fatal: %s", exc)
        raise
    finally:
        publisher.stop()


def main() -> NoReturn:
    _configure_logging()
    settings = load_settings()
    logger.info(
        "vision: starting (source=%s policy=%s classes=%s)",
        settings.source_id,
        settings.policy,
        list(settings.classes) or "all",
    )
    try:
        run(settings)
    except CameraError:
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(0)


if __name__ == "__main__":
    main()
