import unittest

from uavlab.training.openfly_history import transition_history


class HistoryTest(unittest.TestCase):
    def test_initial_and_uniform(self):
        self.assertEqual(transition_history([], 0), [0, 0, 0])
        self.assertEqual(transition_history([1] * 5, 5), [3, 4, 5])

    def test_completed_transitions_only(self):
        self.assertEqual(transition_history([1, 1, 2, 2, 1, 1], 6), [2, 4, 6])
        self.assertEqual(transition_history([1, 1, 2], 3), [0, 2, 3])

    def test_reject_current_or_future_actions(self):
        with self.assertRaises(ValueError):
            transition_history([1, 2], 1)


if __name__ == "__main__":
    unittest.main()
