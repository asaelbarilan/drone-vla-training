"""Two named perception tools and onboard visit evidence; LLM selects all actions."""

import json
from dataclasses import replace

from uavlab.core.mission_evidence import OrderedVisitEvidence, public_ordered_visit
from uavlab.core.registry import register
from uavlab.plugins.reasoning.aerialclaw_visual import AerialClawVisualAgentPolicy


@register("policy", "aerialclaw_ordered_visual")
class AerialClawOrderedVisualPolicy(AerialClawVisualAgentPolicy):
    def __init__(self, **params):
        super().__init__(**params)
        self._ordered = None
        self._object_memory = {}

    @property
    def name(self):
        return "aerialclaw_ordered_visual"

    def reset(self, mission, seed):
        contract = public_ordered_visit(mission)
        if contract is None:
            raise ValueError(
                "ordered visual policy requires the explicit supported two-object instruction"
            )
        self.query = contract.first
        super().reset(mission, seed)
        self.target_label = contract.first
        self._ordered = OrderedVisitEvidence(contract)
        self._object_memory = {}

    def observe_task_evidence(self, observation, scratch):
        if self._ordered is not None:
            self._ordered.observe(observation)
            scratch["ordered_visit_evidence"] = self._ordered

    def _accept_detection_query(self, args):
        if set(args) != {"query"} or args["query"] not in (
            self._ordered.contract.first,
            self._ordered.contract.second,
        ):
            return False
        # Query selection is a model action. Object identity is preserved across calls.
        self.query = self.target_label = args["query"]
        return True

    async def _inspect(self, ctx, trace):
        await super()._inspect(ctx, trace)
        item = self._visual_memory
        if item is not None:
            self._object_memory[self.query] = item
            self._ordered.locate(self.query, item.position, item.t_sim_ns)
        # A not-found result is current-view absence, not deletion of a stationary object.
        ctx.scratch["ordered_visit_evidence"] = self._ordered

    def _context_with_visual_memory(self, ctx):
        items = tuple(
            item
            for item in self._object_memory.values()
            if 0 <= ctx.t_sim_ns - item.t_sim_ns <= 10_000_000_000
        )
        return replace(
            ctx, memory=ctx.memory.model_copy(update={"items": (*ctx.memory.items, *items)})
        )

    def _completion_evidence(self, ctx):
        self.observe_task_evidence(ctx.observation, ctx.scratch)
        supported = self._ordered.stop_supported(ctx.observation)
        return {
            "supported": supported,
            "source": "onboard ordered visit evidence",
            "first_object": self._ordered.contract.first,
            "first_visit_completed": self._ordered.first_completed_t_ns is not None,
            "first_completed_t_ns": self._ordered.first_completed_t_ns,
            "final_object": self._ordered.contract.second,
            "vehicle_speed_mps": ctx.observation.velocity.norm(),
        }

    def _soft_skill_phase(self, ctx, completion):
        return "complete_supported_arrival" if completion["supported"] else "execute_ordered_task"

    def _build_prompt(self, ctx):
        text = super()._build_prompt(ctx)
        text = text[: text.index("## Additional perception hard skill")]
        start = text.index("## Relevant soft skill")
        end = text.index("## BODY-derived coverage reference", start)
        text = (
            text[:start]
            + (
                "## Relevant soft skill: ordered requested perception\n"
                "No automatic detector runs here. Empty detection lists mean no tool result, "
                "not that the objects are absent. Start by requesting detect_object for a "
                "mission object. Scan only rotates the camera; it does not identify objects. "
                "After a not-found result choose a short turn and request detection again. "
                "After localization choose goto, wait for execution feedback and first-object "
                "dwell, then choose skills for the second object. Never treat the first "
                "arrival as mission completion. No fixed route or object positions are supplied.\n\n"
            )
            + text[end:]
        )
        contract = self._ordered.contract
        locations = {
            label: {
                "position_enu_m": pos.model_dump(),
                "source_t_ns": t,
                "age_s": (ctx.t_sim_ns - t) / 1e9,
            }
            for label, (pos, t) in self._ordered.locations.items()
            if self._ordered.location(label, ctx.t_sim_ns) is not None
        }
        return (
            text
            + f"""## Ordered task: model-selected skills
The mission requires visiting {contract.first} first, remaining within {contract.radius_m} m
for {contract.dwell_s} seconds, then visiting {contract.second} and stopping there.
A visit to the first object alone is NOT mission completion. During execute_ordered_task,
you choose detect_object, goto, scan, or hover as needed. You may inspect either object
before choosing movement, but physical visits must respect the mission order.
detect_object accepts exactly {{"query":"{contract.first}"}} or {{"query":"{contract.second}"}}.
It returns one camera-derived position or not-found, without issuing movement.
Object identities stay separate. Not-found refers only to that camera view.
If an object is outside the current view, choose a scan before querying again.
Use goto for your chosen object location; SUPER executes it. You select the next
object/skill after execution feedback. Choose done only when ordered completion
is supported. The first-object dwell fact is measured from odometry, never scoring truth.
First visit completed: {self._ordered.first_completed_t_ns is not None}.
Known stationary object locations (original timestamps, maximum age 30 s):
{json.dumps(locations, sort_keys=True)}
"""
        )

    def _action_protocol_error(self, action, ctx):
        if action.skill == "stop" and not self._ordered.stop_supported(ctx.observation):
            return "ordered stop requires first-object dwell followed by final-object arrival"
        return super()._action_protocol_error(action, ctx)
