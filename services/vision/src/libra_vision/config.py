"""Typed runtime config for the vision service.

All values come from environment / a local `.env`. The same module runs
unchanged on Mac (developer machine) and on Jetson Nano — only the env
differs (camera source, MQTT host, device).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Policy = Literal["on_change", "throttled", "both"]


class VisionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- identity ---------------------------------------------------------
    source_id: str = Field(default="mac-webcam", alias="LIBRA_VISION_SOURCE_ID")

    # ----- camera -----------------------------------------------------------
    # Stored as str so we can accept either an int index ("0") or a URL.
    camera: str = Field(default="0", alias="LIBRA_VISION_CAMERA")
    frame_width: int = Field(default=640, alias="LIBRA_VISION_FRAME_WIDTH")
    frame_height: int = Field(default=480, alias="LIBRA_VISION_FRAME_HEIGHT")
    frame_stride: int = Field(default=2, ge=1, alias="LIBRA_VISION_FRAME_STRIDE")

    # ----- model ------------------------------------------------------------
    model: str = Field(default="yolov8n.pt", alias="LIBRA_VISION_MODEL")
    confidence: float = Field(
        default=0.45, ge=0.0, le=1.0, alias="LIBRA_VISION_CONFIDENCE"
    )
    device: str = Field(default="", alias="LIBRA_VISION_DEVICE")

    # ----- class filter -----------------------------------------------------
    classes_csv: str = Field(default="person", alias="LIBRA_VISION_CLASSES")

    # ----- policy -----------------------------------------------------------
    policy: Policy = Field(default="on_change", alias="LIBRA_VISION_POLICY")
    heartbeat_seconds: float = Field(
        default=10.0, gt=0, alias="LIBRA_VISION_HEARTBEAT_SECONDS"
    )

    # ----- mqtt -------------------------------------------------------------
    mqtt_host: str = Field(default="127.0.0.1", alias="LIBRA_VISION_MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="LIBRA_VISION_MQTT_PORT")
    mqtt_username: str = Field(default="", alias="LIBRA_VISION_MQTT_USERNAME")
    mqtt_password: str = Field(default="", alias="LIBRA_VISION_MQTT_PASSWORD")
    mqtt_topic_prefix: str = Field(
        default="libra/vision", alias="LIBRA_VISION_MQTT_TOPIC_PREFIX"
    )
    mqtt_qos: int = Field(default=1, ge=0, le=2, alias="LIBRA_VISION_MQTT_QOS")

    # ----- derived ----------------------------------------------------------
    @property
    def camera_source(self) -> int | str:
        """Return camera arg suitable for cv2.VideoCapture.

        Numeric strings -> int (local device index). Anything else stays as
        a string (RTSP/HTTP/file path).
        """
        c = self.camera.strip()
        return int(c) if c.isdigit() else c

    @property
    def classes(self) -> tuple[str, ...]:
        items = [c.strip() for c in self.classes_csv.split(",") if c.strip()]
        return tuple(items)

    @property
    def topic_detections(self) -> str:
        return f"{self.mqtt_topic_prefix}/{self.source_id}/detections"

    @property
    def topic_status(self) -> str:
        return f"{self.mqtt_topic_prefix}/{self.source_id}/status"

    @field_validator("device")
    @classmethod
    def _normalize_device(cls, v: str) -> str:
        return v.strip().lower()


def load_settings() -> VisionSettings:
    return VisionSettings()  # type: ignore[call-arg]
