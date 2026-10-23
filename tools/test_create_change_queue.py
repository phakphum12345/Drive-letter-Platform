import unittest

from tools.create_change_queue import (
    RESOURCE_CHANGE_QUEUE_SCHEMA,
    ResourceChangeQueue,
    create_change_queue,
)
from tools.research_os_resource_change_event import ResourceChangeEvent


class CreateChangeQueueTests(unittest.TestCase):
    def test_factory_returns_canonical_queue(self):
        queue = create_change_queue()

        self.assertIsInstance(queue, ResourceChangeQueue)
        self.assertEqual(RESOURCE_CHANGE_QUEUE_SCHEMA, "RESEARCH_OS_RESOURCE_CHANGE_QUEUE_V1")
        self.assertEqual(len(queue), 0)

    def test_factory_seeds_queue_using_canonical_coalescing(self):
        queue = create_change_queue([
            ResourceChangeEvent("z.py", "MODIFY", "test"),
            ResourceChangeEvent("a.py", "CREATE", "test"),
            ResourceChangeEvent("a.py", "MODIFY", "test"),
        ])

        events = queue.drain()
        self.assertEqual(
            [(event.path, event.operation) for event in events],
            [("a.py", "CREATE"), ("z.py", "MODIFY")],
        )

    def test_factory_rejects_non_event_values(self):
        with self.assertRaises(TypeError):
            create_change_queue([{"path": "a.py", "operation": "CREATE"}])


if __name__ == "__main__":
    unittest.main()
