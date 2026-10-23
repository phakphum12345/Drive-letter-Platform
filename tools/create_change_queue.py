"""Compatibility factory for the canonical Research OS resource change queue.

The queue implementation and event validation remain owned by
``tools.research_os_resource_change_queue`` and
``tools.research_os_resource_change_event``. This module deliberately adds no
persistence, filesystem access, resource identity allocation, or execution side
effects.
"""

from __future__ import annotations

from collections.abc import Iterable

from tools.research_os_resource_change_event import ResourceChangeEvent
from tools.research_os_resource_change_queue import (
    RESOURCE_CHANGE_QUEUE_SCHEMA,
    ResourceChangeQueue,
)


def create_change_queue(
    events: Iterable[ResourceChangeEvent] = (),
) -> ResourceChangeQueue:
    """Create a queue and optionally seed it with validated change events.

    ``ResourceChangeQueue`` remains the source of truth for event type checks,
    deterministic ordering, and coalescing behavior.
    """
    queue = ResourceChangeQueue()
    queue.extend(events)
    return queue


__all__ = [
    "RESOURCE_CHANGE_QUEUE_SCHEMA",
    "ResourceChangeQueue",
    "create_change_queue",
]
