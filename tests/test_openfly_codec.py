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
