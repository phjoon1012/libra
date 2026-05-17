"""MQTT event publisher.

- Publishes detections to {prefix}/{source_id}/detections.
- Publishes a retained status message to {prefix}/{source_id}/status:
  "online" on connect, "offline" via the broker's Last-Will-and-Testament
  if this process disappears uncleanly.
- Background loop (paho's loop_start) handles reconnects.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

from .detector import Detection

logger = logging.getLogger(__name__)


@dataclass
class PublisherConfig:
    host: str
    port: int
    username: str
    password: str
    topic_detections: str
    topic_status: str
    qos: int
    source_id: str
    client_id: str


class MqttPublisher:
    def __init__(self, cfg: PublisherConfig) -> None:
        self._cfg = cfg
        # CallbackAPIVersion.VERSION2 is the new API in paho-mqtt 2.x.
        self._client = mqtt.Client(
            client_id=cfg.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if cfg.username:
            self._client.username_pw_set(cfg.username, cfg.password or None)
        # LWT: broker auto-publishes "offline" if we die without a clean
        # disconnect. Retained so a late subscriber still sees the
        # last-known state.
        self._client.will_set(
            cfg.topic_status,
            payload=json.dumps({"status": "offline"}),
            qos=cfg.qos,
            retain=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        logger.info(
            "vision: connecting to mqtt %s:%d (client_id=%s)",
            self._cfg.host,
            self._cfg.port,
            self._cfg.client_id,
        )
        self._client.connect_async(self._cfg.host, self._cfg.port, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._publish_status("offline", retain=True)
        finally:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("vision: mqtt stopped")

    def publish_detections(
        self,
        *,
        frame_id: int,
        detections: list[Detection],
        reason: str,
    ) -> None:
        payload = {
            "source": self._cfg.source_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "frame_id": frame_id,
            "reason": reason,
            "summary": _summarize(detections),
            "detections": [
                {
                    "label": d.label,
                    "confidence": round(d.confidence, 3),
                    "bbox": list(d.bbox),
                }
                for d in detections
            ],
        }
        self._client.publish(
            self._cfg.topic_detections,
            payload=json.dumps(payload),
            qos=self._cfg.qos,
            retain=False,
        )

    # ---------------- callbacks --------------------------------------------

    def _on_connect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        rc = getattr(reason_code, "value", reason_code)
        if rc != 0:
            logger.error("vision: mqtt connect failed rc=%s", reason_code)
            return
        logger.info("vision: mqtt connected → %s", self._cfg.topic_detections)
        self._publish_status("online", retain=True)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        logger.warning("vision: mqtt disconnected (rc=%s) — paho will retry", reason_code)

    def _publish_status(self, status: str, *, retain: bool) -> None:
        self._client.publish(
            self._cfg.topic_status,
            payload=json.dumps({"status": status, "source": self._cfg.source_id}),
            qos=self._cfg.qos,
            retain=retain,
        )


def _summarize(detections: list[Detection]) -> str:
    if not detections:
        return "nothing"
    counts = Counter(d.label for d in detections)
    parts = [f"{n} {label}{'s' if n > 1 and not label.endswith('s') else ''}"
             for label, n in counts.most_common()]
    return ", ".join(parts)
