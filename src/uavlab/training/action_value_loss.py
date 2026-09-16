"""Explicit answer-value weighting; never infer spans from numeric token IDs."""

import re

from uavlab.training.direct_vla_frd import FIELDS


def value_token_weights(text, offsets, *, trailing_tokens=1):
    """Return weights totaling1:90% across five fields,10% syntax/EOS.

    Offsets must come from the exact tokenization of the canonical answer.
    Tokens crossing a field-value boundary are rejected, not silently weighted.
    """
    matches = list(re.finditer(r'"([a-z_]+)":(true|false|[0-9]+)', text))
    if [m.group(1) for m in matches] != [*FIELDS, "stop"]:
        raise ValueError("canonical FRD field order required")
    assignments = [None] * len(offsets)
    counts = {k: 0 for k in (*FIELDS, "stop")}
    for i, (start, end) in enumerate(offsets):
        if not 0 <= start < end <= len(text):
            raise ValueError("invalid token offsets")
        for match in matches:
            low, high = match.span(2)
            if start < high and end > low:
                if start < low or end > high:
                    raise ValueError("token crosses value boundary")
                assignments[i] = match.group(1)
                counts[match.group(1)] += 1
    if not all(counts.values()) or trailing_tokens < 1:
        raise ValueError("missing value tokens or EOS")
    grammar = assignments.count(None) + trailing_tokens
    weights = [0.18 / counts[k] if k else 0.1 / grammar for k in assignments]
    weights += [0.1 / grammar] * trailing_tokens
    return weights, assignments + [None] * trailing_tokens
