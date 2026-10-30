import unittest

from orchestrator.core import PER_CHAT_WORKERS, active_workers_for_chat, chat_at_worker_cap


def _rows(supervisor_id, job_id, count, phase='implement', state='running'):
    return [{'state': state, 'supervisor_id': supervisor_id, 'job_id': job_id, 'phase': phase} for _ in range(count)]


class PerChatCapacityTests(unittest.TestCase):
    def test_helper_caps_each_supervisor_across_jobs(self):
        self.assertEqual(PER_CHAT_WORKERS, 10)
        full_a = _rows('A', 'job-a', 10) + _rows('B', 'job-b', 0)
        self.assertTrue(chat_at_worker_cap(full_a, 'A', 'job-a'))
        self.assertFalse(chat_at_worker_cap(full_a, 'B', 'job-b'))
        self.assertEqual(active_workers_for_chat(full_a, 'A', 'job-a'), 10)
        self.assertEqual(active_workers_for_chat(full_a, 'B', 'job-b'), 0)
        nine_a = _rows('A', 'job-a', 9)
        self.assertFalse(chat_at_worker_cap(nine_a, 'A', 'job-a'))
        self.assertEqual(active_workers_for_chat(nine_a, 'A', 'job-a'), 9)
        split = _rows('A', 'job-1', 6) + _rows('A', 'job-2', 4, phase='review', state='launching')
        self.assertEqual(active_workers_for_chat(split, 'A', 'job-1'), 10)
        self.assertEqual(active_workers_for_chat(split, 'A', 'job-2'), 10)
        self.assertTrue(chat_at_worker_cap(split, 'A', 'job-1'))
        self.assertTrue(chat_at_worker_cap(split, 'A', 'job-2'))
        almost = _rows('A', 'job-1', 5) + _rows('A', 'job-2', 4, phase='review', state='waiting_permission')
        self.assertEqual(active_workers_for_chat(almost, 'A', 'job-1'), 9)
        self.assertFalse(chat_at_worker_cap(almost, 'A', 'job-1'))


if __name__ == '__main__':
    unittest.main()
