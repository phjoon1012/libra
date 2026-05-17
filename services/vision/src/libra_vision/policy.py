"""Event emission policy.

Decides whether the current detection set warrants publishing an event.
Three modes:

- on_change : only when the set of labels (or per-label counts) changes.
- throttled : at a fixed interval, regardless of activity.
- both      : on_change AND a heartbeat tick.

Lifecycle is single-threaded; instantiate once per service.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Literal

Policy = Literal["on_change", "throttled", "both"]

# Per-label count signature, deterministic order.
LabelSignature = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Decision:
    emit: bool
    reason: str  # "change", "heartbeat", or "skip"


def _signature(labels: list[str]) -> LabelSignature:
    counts = Counter(labels)
    return tuple(sorted(counts.items()))


class EmissionPolicy:
    def __init__(
        self,
        *,
        mode: Policy = "on_change",
        heartbeat_seconds: float = 10.0,
    ) -> None:
        self._mode = mode
        self._heartbeat = heartbeat_seconds
        self._last_signature: LabelSignature | None = None
        self._last_emit_ts: float = 0.0

    def evaluate(self, labels: list[str]) -> Decision:
        now = time.monotonic()
        sig = _signature(labels)
        changed = sig != self._last_signature
        heartbeat_due = (now - self._last_emit_ts) >= self._heartbeat

        emit = False
        reason = "skip"
        if self._mode in ("on_change", "both") and changed:
            emit, reason = True, "change"
        elif self._mode in ("throttled", "both") and heartbeat_due:
            emit, reason = True, "heartbeat"

        if emit:
            self._last_signature = sig
            self._last_emit_ts = now
        elif self._last_signature is None:
            # First evaluation: record signature so we don't fire change
            # on every empty frame at startup.
            self._last_signature = sig
            self._last_emit_ts = now
        return Decision(emit=emit, reason=reason)
