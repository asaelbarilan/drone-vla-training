"""Read TF Example episode identity while skipping length-delimited image fields.

The caller supplies a bounded random-access reader. This does not verify the
TFRecord payload CRC: a complete payload must be downloaded for that check.
"""


def varint(read, offset, end):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= end:
            raise ValueError("Truncated protobuf varint")
        byte = read(offset, 1)[0]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise ValueError("Protobuf varint exceeds 64 bits")


def fields(read, start, end):
    offset = start
    while offset < end:
        tag, offset = varint(read, offset, end)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("Invalid protobuf field number")
        if wire == 2:
            length, offset = varint(read, offset, end)
            stop = offset + length
            if stop > end:
                raise ValueError("Protobuf field escapes enclosing message")
            yield number, wire, offset, stop
            offset = stop
        elif wire == 0:
            value, offset = varint(read, offset, end)
            yield number, wire, value, value
        elif wire in (1, 5):
            stop = offset + (8 if wire == 1 else 4)
            if stop > end:
                raise ValueError("Truncated fixed-size protobuf field")
            yield number, wire, offset, stop
            offset = stop
        else:
            raise ValueError("Unsupported protobuf wire type")


def identity_features(read, start, size):
    """Return source file path and episode ID; never decode an image Feature."""
    result = {}
    targets = {"episode_metadata/file_path", "episode_metadata/episode_id"}
    for n, w, parent_start, parent_end in fields(read, start, start + size):
        if n != 1 or w != 2:  # Example.features
            continue
        for n, w, a, b in fields(read, parent_start, parent_end):
            if n != 1 or w != 2:  # Features.feature map entries
                continue
            entry = list(fields(read, a, b))
            keys = [f for f in entry if f[:2] == (1, 2)]
            values = [f for f in entry if f[:2] == (2, 2)]
            if len(keys) != 1 or len(values) != 1:
                raise ValueError("Malformed Feature map entry")
            _, _, ka, kb = keys[0]
            if kb - ka > 256:
                raise ValueError("Unexpectedly long Feature key")
            key = read(ka, kb - ka).decode("utf-8")
            if key not in targets:
                continue
            if key in result:
                raise ValueError("Duplicate identity Feature")
            _, _, va, vb = values[0]
            feature = list(fields(read, va, vb))
            expected_type = 1 if key.endswith("file_path") else 3
            if len(feature) != 1 or feature[0][:2] != (expected_type, 2):
                raise ValueError("Wrong identity Feature type")
            _, _, la, lb = feature[0]
            items = list(fields(read, la, lb))
            if len(items) != 1 or items[0][:2] != (1, 2):
                raise ValueError("Expected a single identity value")
            _, _, ia, ib = items[0]
            if key.endswith("file_path"):
                if ib - ia > 4096:
                    raise ValueError("Unexpectedly long route identity")
                result[key] = read(ia, ib - ia).decode("utf-8")
            else:
                result[key], end = varint(read, ia, ib)
                if end != ib:
                    raise ValueError("Expected one episode ID")
    if result.keys() != targets:
        raise ValueError("Missing episode identity")
    return result
