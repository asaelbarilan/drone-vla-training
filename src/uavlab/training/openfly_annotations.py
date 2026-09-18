"""Parse source phases explicitly; do not turn phase tags into flight commands."""

import math


def annotation_contract(episode):
    actions, positions, yaws = episode["action"], episode["pos"], episode["yaw"]
    if not (len(actions) == len(positions) == len(yaws) == len(episode["index_list"])):
        raise ValueError("Annotation fields have different lengths")
    if actions.count(0) != 1:
        raise ValueError("Expected one navigation STOP")
    xyz = []
    for pos, yaw in zip(positions, yaws, strict=True):
        if len(pos) not in (3, 4):
            raise ValueError("Unknown position schema")
        if len(pos) == 4 and abs((pos[3] - yaw + math.pi) % (2 * math.pi) - math.pi) > 1e-5:
            raise ValueError("Fourth position component disagrees with separate yaw")
        xyz.append(list(pos[:3]))
    stop = actions.index(0)
    first = 0
    while first < stop and actions[first] == -1:
        first += 1
    if any(a not in range(1, 10) for a in actions[first:stop]):
        raise ValueError("Unsupported tag inside navigation phase")
    if any(a != -2 for a in actions[stop + 1 :]):
        raise ValueError("Only the explicit descent phase may follow navigation STOP")
    return dict(
        navigation_annotation_start=first,
        navigation_stop_index=stop,
        initial_climb_indices=list(range(first)),
        post_stop_descent_indices=list(range(stop + 1, len(actions))),
        navigation_goal_xyz=xyz[stop],
        last_recorded_xyz=xyz[-1],
        xyz=xyz,
        note="Annotation indices are not verified macro start frames. Phase tags remain metadata, "
        "not inferred velocity labels or executable landing commands.",
    )
