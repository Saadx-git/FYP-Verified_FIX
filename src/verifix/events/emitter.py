from __future__ import annotations

import json
import time
from typing import IO, Any

SCHEMA_VERSION = 1


class EventEmitter:
    """Emits versioned JSONL events (consumed by the VS Code extension and logs)."""

    def __init__(self, stream: IO[str] | None = None) -> None:
        self.stream = stream
        self.events: list[dict[str, Any]] = []

    def emit(self, type: str, **data: Any) -> dict[str, Any]:
        event = {"v": SCHEMA_VERSION, "ts": time.time(), "type": type, "data": data}
        self.events.append(event)
        if self.stream is not None:
            self.stream.write(json.dumps(event, default=str) + "\n")
            self.stream.flush()
        return event
