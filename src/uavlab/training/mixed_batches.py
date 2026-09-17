"""Equal-task effective batches; sampler never accepts validation for optimization."""

import random

from uavlab.training.direct_vla_frd import FIELDS
from uavlab.training.splits import check_collection_range

GROUPS = ("visual", "motion", "hold", "stop")


def task_class(row):
    if row["task_group"] == "visual":
        return "visual"
    if row["target"]["stop"]:
        return "stop"
    return "hold" if all(row["target"][k] == 32 for k in FIELDS) else "motion"


def balanced_schedule(rows, updates, seed=138):
    if updates < 1:
        raise ValueError("positive update count required")
    rng = random.Random(seed)
    pools = {group: [] for group in GROUPS}
    seen = set()
    for row in rows:
        identity = row["decision_id"]
        if identity in seen:
            raise ValueError("duplicate identity")
        seen.add(identity)
        if row["split"] != "train":
            continue
        check_collection_range(row["seed"], 1)
        if row["seed"] in range(1060, 1065) or row["seed"] % 5 == 0:
            raise ValueError("validation/protected seed labelled train")
        pools[task_class(row)].append(identity)
    if not all(pools.values()):
        raise ValueError("each of the four training groups is required")
    queues = {group: [] for group in GROUPS}
    schedule = []
    for _ in range(updates):
        batch = []
        for group in GROUPS:
            if not queues[group]:
                queues[group] = list(pools[group])
                rng.shuffle(queues[group])
            batch.append(queues[group].pop())
        rng.shuffle(batch)
        schedule.append(batch)
    return schedule


def backward_mixed_batch(identities, by_id, loss_for_row):
    """Accumulate mean-of-four gradients; caller zeroes/steps/clips once per batch.

    Sequential microbatches avoid padding and peak-memory growth. Every loss is
    normalized within its sample, then equally across the four task groups.
    """
    if len(identities) != 4 or set(task_class(by_id[k]) for k in identities) != set(GROUPS):
        raise ValueError("effective batch must contain exactly one example per task")
    if any(by_id[k]["split"] != "train" for k in identities):
        raise ValueError("validation example in optimizer batch")
    values = []
    for identity in identities:
        loss = loss_for_row(by_id[identity])
        if not loss.isfinite().item():
            raise ValueError("nonfinite microbatch loss")
        (loss / 4).backward()
        values.append(float(loss.detach()))
    return sum(values) / 4
