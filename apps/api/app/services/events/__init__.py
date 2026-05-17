"""Event layer.

Receives events from edge devices (vision, future Pi satellites,
smart-home, etc.) and routes them inside the brain.

v0 just logs to API stdout. The bridge is structured so we can later
add an in-process event bus, persist events, or fan out to memory/UI
without touching the publishers.
"""

from .vision_bridge import (
    VisionEventBridge,
    get_vision_bridge,
    start_vision_bridge,
    stop_vision_bridge,
)

__all__ = [
    "VisionEventBridge",
    "get_vision_bridge",
    "start_vision_bridge",
    "stop_vision_bridge",
]
