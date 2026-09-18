import unittest

from uavlab.training.openfly_annotations import annotation_contract


class TestAnnotationContract(unittest.TestCase):
    def episode(self, actions):
        return dict(
            action=actions,
            pos=[[0, 0, 3 * i] for i in range(len(actions))],
            yaw=[0] * len(actions),
            index_list=[str(i) for i in range(len(actions))],
        )

    def test_goal_is_mission_stop_before_descent(self):
        e = self.episode([-1, 1, 0, -2, -2])
        r = annotation_contract(e)
        self.assertEqual(r["navigation_goal_xyz"], e["pos"][2])
        self.assertNotEqual(r["navigation_goal_xyz"], r["last_recorded_xyz"])
        self.assertEqual(r["initial_climb_indices"], [0])
        self.assertEqual(r["post_stop_descent_indices"], [3, 4])

    def test_reject_internal_unsupported_phase(self):
        with self.assertRaises(ValueError):
            annotation_contract(self.episode([1, -1, 0]))

    def test_mixed_pose_schema_requires_matching_yaw(self):
        e = self.episode([1, 0])
        e["pos"][0].append(0)
        self.assertEqual(annotation_contract(e)["xyz"], [[0, 0, 0], [0, 0, 3]])
        e["pos"][0][3] = 1
        with self.assertRaises(ValueError):
            annotation_contract(e)

    def test_reject_ambiguous_mission_stop(self):
        with self.assertRaises(ValueError):
            annotation_contract(self.episode([1, 0, 0]))


if __name__ == "__main__":
    unittest.main()
