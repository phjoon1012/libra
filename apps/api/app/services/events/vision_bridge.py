"""MQTT → brain bridge for vision events.

Subscribes to the configured vision topic filter and logs every payload
to API stdout. Future iterations can:

  - persist events to Postgres,
  - publish on an in-process pub/sub for the dashboard,
  - inject "saw a person 30s ago" facts into long-term memory,

…all by adding handlers in :py:meth:`VisionEventBridge._on_detections`
without touching the publishers.

The bridge owns its own paho client and runs on paho's internal thread
loop. We keep the surface area minimal so the rest of the API stays
free of MQTT concerns.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class VisionEvent:
    source: str
    ts: str
    frame_id: int
    reason: str  # "change" | "heartbeat" | ...
    summary: str
    detections: list[dict[str, Any]]

    @classmethod
    def from_payload(cls, body: bytes) -> "VisionEvent | None":
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        try:
            return cls(
                source=str(data["source"]),
                ts=str(data.get("ts", "")),
                frame_id=int(data.get("frame_id", 0)),
                reason=str(data.get("reason", "")),
                summary=str(data.get("summary", "")),
                detections=list(data.get("detections") or []),
            )
        except (KeyError, TypeError, ValueError):
            return None


class VisionEventBridge:
    """Subscribes to vision MQTT topics and logs incoming events.

    Designed to be a singleton owned by the FastAPI lifespan. `start()`
    is non-blocking — paho runs its own loop thread.
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._client: mqtt.Client | None = None
        self._started = False

    # ----- lifecycle --------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        if not self._s.vision_enabled:
            logger.info("vision bridge: disabled via LIBRA_VISION_ENABLED")
            return

        client = mqtt.Client(
            client_id="libra-api-vision-bridge",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if self._s.mqtt_username:
            client.username_pw_set(
                self._s.mqtt_username, self._s.mqtt_password or None
            )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        logger.info(
            "vision bridge: connecting to mqtt %s:%d → %s",
            self._s.mqtt_host,
            self._s.mqtt_port,
            self._s.vision_topic_filter,
        )
        try:
            client.connect_async(
                self._s.mqtt_host, self._s.mqtt_port, keepalive=30
            )
        except Exception as exc:  # pragma: no cover — network blip
            logger.warning("vision bridge: connect_async failed: %s", exc)
            return

        client.loop_start()
        self._client = client
        self._started = True

    def stop(self) -> None:
        client = self._client
        if not client:
            return
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:  # pragma: no cover
            pass
        finally:
            self._client = None
            self._started = False
            logger.info("vision bridge: stopped")

    # ----- callbacks --------------------------------------------------------

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        # paho 2.x gives a ReasonCode object; older versions / non-V2
        # callbacks give a plain int. .value is the int code in both.
        rc = getattr(reason_code, "value", reason_code)
        if rc != 0:
            logger.error("vision bridge: connect failed rc=%s", reason_code)
            return
        client.subscribe(
            [
                (self._s.vision_topic_filter, 1),
                (self._s.vision_status_topic_filter, 1),
            ]
        )
        logger.info(
            "vision bridge: connected, subscribed to %s & %s",
            self._s.vision_topic_filter,
            self._s.vision_status_topic_filter,
        )

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        logger.warning(
            "vision bridge: disconnected (rc=%s) — paho will retry", reason_code
        )

    def _on_message(
        self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage
    ) -> None:
        topic = msg.topic
        if topic.endswith("/status"):
            self._on_status(topic, msg.payload)
            return
        if topic.endswith("/detections"):
            self._on_detections(topic, msg.payload)
            return
        logger.debug("vision bridge: ignoring %s", topic)

    # ----- handlers (override in tests / extend in v0.4.x) ------------------

    def _on_status(self, topic: str, body: bytes) -> None:
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("vision bridge: bad status payload on %s", topic)
            return
        logger.info(
            "vision status: %s = %s",
            topic,
            data.get("status", "?"),
        )

    def _on_detections(self, topic: str, body: bytes) -> None:
        event = VisionEvent.from_payload(body)
        if event is None:
            logger.warning("vision bridge: bad detection payload on %s", topic)
            return
        logger.info(
            "vision event (%s/%s): %s [frame=%d, %d detection(s)]",
            event.source,
            event.reason,
            event.summary,
            event.frame_id,
            len(event.detections),
        )


# Module-level singleton -------------------------------------------------------

_BRIDGE: VisionEventBridge | None = None


def get_vision_bridge() -> VisionEventBridge | None:
    return _BRIDGE


def start_vision_bridge(settings: Settings) -> VisionEventBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = VisionEventBridge(settings)
    _BRIDGE.start()
    return _BRIDGE


def stop_vision_bridge() -> None:
    global _BRIDGE
    if _BRIDGE is not None:
        _BRIDGE.stop()
        _BRIDGE = None
