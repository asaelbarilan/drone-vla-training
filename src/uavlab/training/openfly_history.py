"""Causal diagnostic history; not the paper's unpublished landmark filter."""


def transition_history(completed_actions, current_frame):
    """Only actions already executed may determine historical image indices."""
    if len(completed_actions) != current_frame:
        raise ValueError("Require exactly the completed action prefix, no current/future labels")
    keys = [i for i in range(1, current_frame) if completed_actions[i] != completed_actions[i - 1]]
    past = [max(0, current_frame - 2), max(0, current_frame - 1)] if not keys else [0, *keys][-2:]
    return [*past, current_frame]


def direction(action):
    return 1 if action in (8, 9) else action
