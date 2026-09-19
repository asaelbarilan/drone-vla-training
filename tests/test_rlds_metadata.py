import pytest

from uavlab.training.rlds_metadata import identity_features


def vi(n):
    b = bytearray()
    while n > 127:
        b.append((n & 127) | 128)
        n >>= 7
    b.append(n)
    return bytes(b)


def field(n, data):
    return vi((n << 3) | 2) + vi(len(data)) + data


def entry(key, value, reverse=False):
    k, v = field(1, key.encode()), field(2, value)
    return field(1, v + k if reverse else k + v)


@pytest.mark.parametrize("reverse", [True, False])
def test_sparse_reader_skips_image_payload_and_finds_reordered_metadata(reverse):
    image = b"not-a-real-image" * 100000
    path = "source/env_airsim_18/development-route"
    data = field(
        1,
        entry("steps/observation/image_1", field(1, field(1, image)), reverse)
        + entry("episode_metadata/file_path", field(1, field(1, path.encode())), reverse)
        + entry("episode_metadata/episode_id", field(3, field(1, vi(1028))), reverse),
    )
    reads = []

    def read(start, size):
        reads.append((start, size))
        return data[start : start + size]

    result = identity_features(read, 0, len(data))
    assert result == {"episode_metadata/file_path": path, "episode_metadata/episode_id": 1028}
    assert sum(n for _, n in reads) < 250
    image_start = data.index(image)
    assert all(a + n <= image_start or a >= image_start + len(image) for a, n in reads)


def test_malformed_lengths_are_rejected_before_reading_outside_payload():
    data = b"\x0a\xff\x7f"
    with pytest.raises(ValueError, match="escapes"):
        identity_features(lambda a, n: data[a : a + n], 0, len(data))


def test_missing_identity_is_not_inferred_from_shard_name():
    data = field(1, entry("steps/observation/image_1", field(1, field(1, b"image"))))
    with pytest.raises(ValueError, match="Missing"):
        identity_features(lambda a, n: data[a : a + n], 0, len(data))
