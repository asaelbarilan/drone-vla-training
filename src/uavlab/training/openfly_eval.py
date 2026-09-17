"""Coarse action scoring for cross-interface OpenFly transfer diagnostics."""

from collections import Counter


def native_class(values):
    """Classify the rounded native8vector by its sole active component; no units conversion."""
    if len(values) != 8 or any(type(v) is not int or v < 0 for v in values):
        return "invalid"
    active = [i for i, v in enumerate(values) if v != 0]
    if len(active) != 1:
        return "hold" if not active else "mixed"
    i = active[0]
    if i == 0 and values[i] != 1:
        return "invalid"
    return ("stop", "forward", "left_turn", "right_turn", "up", "down", "left", "right")[i]


def frd_class(parsed):
    if parsed is None:
        return "invalid"
    if parsed["stop"]:
        return "stop"
    values = [parsed[k] - 32 for k in ("forward_bin", "right_bin", "down_bin", "yaw_cw_bin")]
    active = [i for i, v in enumerate(values) if v != 0]
    if len(active) != 1:
        return "hold" if not active else "mixed"
    i = active[0]
    return (
        ("backward", "forward"),
        ("left", "right"),
        ("up", "down"),
        ("left_turn", "right_turn"),
    )[i][values[i] > 0]


def score(rows, predicted):
    assert len(rows) == len(predicted)
    groups = {}
    for split in ("all", "seen", "unseen"):
        indices = [i for i, r in enumerate(rows) if split == "all" or r["split"] == split]
        truth = Counter(rows[i]["target_class"] for i in indices)
        confusion = {}
        for i in indices:
            key = rows[i]["target_class"] + " -> " + predicted[i]
            confusion[key] = confusion.get(key, 0) + 1
        recalls = {
            c: sum(rows[i]["target_class"] == c and predicted[i] == c for i in indices) / n
            for c, n in truth.items()
        }
        groups[split] = dict(
            n=len(indices),
            correct=sum(predicted[i] == rows[i]["target_class"] for i in indices),
            macro_recall=sum(recalls.values()) / len(recalls),
            per_class_recall=recalls,
            false_stop=sum(
                predicted[i] == "stop" and rows[i]["target_class"] != "stop" for i in indices
            ),
            nonterminal=sum(rows[i]["target_class"] != "stop" for i in indices),
            invalid=sum(predicted[i] == "invalid" for i in indices),
            mixed=sum(predicted[i] == "mixed" for i in indices),
            majority_class=max(truth, key=truth.get),
            majority_correct=max(truth.values()),
            confusion=confusion,
        )
    return groups
