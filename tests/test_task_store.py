import unittest
import threading
import time
from core.task_store import TaskStore, TaskStatus, TaskConflictError


class TestTaskStore(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()

    def test_create_and_get_task_snapshot(self):
        task_snap = self.store.create_task(task_id="task_1", module_id="test_mod", filename="test.mp4")
        self.assertEqual(task_snap["id"], "task_1")
        self.assertEqual(task_snap["module_id"], "test_mod")
        self.assertEqual(task_snap["status"], "pending")
        self.assertEqual(task_snap["filename"], "test.mp4")

        fetched = self.store.get_task("task_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], "task_1")

    def test_defensive_snapshot_mutation(self):
        task_snap = self.store.create_task(task_id="task_snap", filename="original.mp4")
        # Mutate returned snapshot dictionary
        task_snap["filename"] = "mutated.mp4"
        task_snap["status"] = "completed"

        # Check internal TaskStore state remains unchanged
        refetched = self.store.get_task("task_snap")
        self.assertEqual(refetched["filename"], "original.mp4")
        self.assertEqual(refetched["status"], "pending")

    def test_update_task_status_and_progress(self):
        self.store.create_task(task_id="task_update")
        updated = self.store.update_task("task_update", status=TaskStatus.DOWNLOADING, progress=45.5, speed="1.2 MB/s")
        self.assertTrue(updated)

        fetched = self.store.get_task("task_update")
        self.assertEqual(fetched["status"], "downloading")
        self.assertEqual(fetched["progress"], 45.5)
        self.assertEqual(fetched["speed"], "1.2 MB/s")

    def test_cancel_event_behavior(self):
        self.store.create_task(task_id="task_cancel")
        cancel_event = self.store.get_cancel_event("task_cancel")
        self.assertIsNotNone(cancel_event)
        self.assertFalse(cancel_event.is_set())
        self.assertFalse(self.store.is_canceled("task_cancel"))

        canceled = self.store.cancel_task("task_cancel")
        self.assertTrue(canceled)
        self.assertTrue(cancel_event.is_set())
        self.assertTrue(self.store.is_canceled("task_cancel"))

        fetched = self.store.get_task("task_cancel")
        self.assertEqual(fetched["status"], "canceled")

    def test_concurrent_updates_without_race_failures(self):
        self.store.create_task(task_id="concurrent_task", progress=0.0)
        num_threads = 20
        updates_per_thread = 50

        def worker_func():
            for _ in range(updates_per_thread):
                t_snap = self.store.get_task("concurrent_task")
                if t_snap:
                    curr = t_snap.get("progress", 0.0)
                    self.store.update_task("concurrent_task", progress=curr + 1.0)
                time.sleep(0.001)

        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=worker_func)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        final = self.store.get_task("concurrent_task")
        self.assertIsNotNone(final)
        self.assertGreater(final["progress"], 0.0)

    def test_task_metrics_persistence(self):
        # Create task with metrics
        self.store.create_task(task_id="t_metrics", metrics={"test_metric": 42})
        fetched = self.store.get_task("t_metrics")
        self.assertEqual(fetched["metrics"], {"test_metric": 42})

        # Update metrics
        self.store.update_task("t_metrics", metrics={"updated_metric": 100})
        refetched = self.store.get_task("t_metrics")
        self.assertEqual(refetched["metrics"], {"updated_metric": 100})

    def test_task_workflow_config_persistence(self):
        config_data = {"name": "Test Workflow", "steps": []}
        self.store.create_task(task_id="t_wf_config", workflow_config=config_data)
        fetched = self.store.get_task("t_wf_config")
        self.assertEqual(fetched["workflow_config"], config_data)

        # Defensive copy check
        config_data["name"] = "Mutated name"

        refetched = self.store.get_task("t_wf_config")
        self.assertEqual(refetched["workflow_config"]["name"], "Test Workflow")

    def test_clear_idle_tasks(self):
        self.store.create_task(task_id="t1", status=TaskStatus.COMPLETED)
        self.store.create_task(task_id="t2", status=TaskStatus.FAILED)
        cleared = self.store.clear_idle_tasks()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(self.store.get_all_tasks()), 0)

    def test_create_task_conflict_rejection(self):
        # Create a task with a source_key in pending status
        self.store.create_task(task_id="w1", module_id="workflow", source_key="video_key_1", status=TaskStatus.PENDING)
        
        # Creating another task with the same source_key should raise TaskConflictError
        with self.assertRaises(TaskConflictError):
            self.store.create_task(task_id="w2", module_id="workflow", source_key="video_key_1")
            
        # Update the task status to processing
        self.store.update_task("w1", status=TaskStatus.PROCESSING)
        
        # Still conflicting
        with self.assertRaises(TaskConflictError):
            self.store.create_task(task_id="w3", module_id="workflow", source_key="video_key_1")
            
        # Completed task should not conflict
        self.store.update_task("w1", status=TaskStatus.COMPLETED)
        t_snap = self.store.create_task(task_id="w4", module_id="workflow", source_key="video_key_1")
        self.assertEqual(t_snap["id"], "w4")




if __name__ == "__main__":
    unittest.main()
