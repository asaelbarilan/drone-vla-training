import unittest

from uavlab.training.openfly_codec import OpenFlyCodec


def config(high):
    return {
        "norm_stats": {
            "test": {
                "action": {
                    "q01": [0] * 8,
                    "q99": high,
                    "min": [0] * 8,
                    "max": high,
                    "mask": [True] * 8,
                }
            }
        },
        "n_action_bins": 256,
        "text_config": {"vocab_size": 32064},
        "pad_to_multiple_of": 64,
    }


class TestOpenFlyCodec(unittest.TestCase):
    def test_vertical_and_forward_primitives_roundtrip(self):
        codec = OpenFlyCodec(config([1, 9, 15, 15, 2, 2, 0, 0]), "test")
        self.assertEqual(
            codec.require_coverage([0, 1, 2, 3, 4, 5, 8, 9])["roundtrip_actions"],
            [0, 1, 2, 3, 4, 5, 8, 9],
        )

    def test_reject_silent_vertical_collapse(self):
        codec = OpenFlyCodec(config([1, 9, 15, 15, 0, 0, 0, 0]), "test")
        with self.assertRaisesRegex(ValueError, r"\[4, 5\]"):
            codec.require_coverage([0, 1, 2, 3, 4, 5])

    def test_vertical_coverage_does_not_validate_horizontal_tokens(self):
        horizontal = OpenFlyCodec(config([1, 9, 15, 15, 0, 0, 0, 0]), "test")
        vertical = OpenFlyCodec(config([1, 9, 15, 15, 2, 2, 0, 0]), "test")
        tokens = horizontal.encode(9)
        self.assertEqual(horizontal.decode(tokens)["action_id"], 9)
        wrong = vertical.decode(tokens)
        self.assertIsNone(wrong["action_id"])
        self.assertEqual(wrong["rounded"][4:6], [1, 1])
        vertical.require_coverage([0, 1, 2, 3, 4, 5, 8, 9])
        with self.assertRaisesRegex(ValueError, "source action statistics"):
            vertical.require_source_statistics(horizontal.stats)
        self.assertTrue(
            horizontal.require_source_statistics(horizontal.stats)["source_statistics_verified"]
        )

    def test_zero_vector_does_not_become_stop(self):
        codec = OpenFlyCodec(config([1, 9, 15, 15, 2, 2, 0, 0]), "test")
        self.assertIsNone(codec.decode([31999] * 8)["action_id"])

    def test_reject_early_eos_and_nonaction_tokens(self):
        codec = OpenFlyCodec(config([1, 9, 15, 15, 2, 2, 0, 0]), "test")
        for tokens in ([31999] * 7, [31999] * 7 + [2]):
            with self.assertRaises(ValueError):
                codec.decode(tokens)

    def test_mixed_vector_is_not_projected_to_an_action(self):
        codec = OpenFlyCodec(config([1, 9, 15, 15, 2, 2, 0, 0]), "test")
        tokens = codec.encode(4)
        tokens[1] = codec.encode(9)[1]
        self.assertIsNone(codec.decode(tokens)["action_id"])


if __name__ == "__main__":
    unittest.main()
