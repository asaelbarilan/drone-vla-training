"""Paper-faithful AerialClaw-style closed-loop skill agent.

The policy owns semantic mission authority only. A real LLM chooses one bounded
hard skill from documented state; :mod:`uavlab.core.skills` validates and
expands it, and the shared router/SUPER/controller stack owns every metre of
motion. There is deliberately no local command parser or scripted fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    SkillCall,
    StrictModel,
    Vec3,
    s_to_ns,
)
from uavlab.core.mission_evidence import public_coordinate_goal
from uavlab.core.registry import register
from uavlab.core.sensing import widest_free_bearing
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import (
    DecisionContext,
    InferenceRequest,
    SemanticCompletionEvidence,
)


class AerialClawUnavailable(RuntimeError):
    """The declared real model/runtime resource is absent or inconsistent."""


class AerialClawOutputError(RuntimeError):
    """The model failed to produce a valid inspectable agent decision."""


class _AgentAction(StrictModel):
    skill: str
    args: dict[str, float | str | bool] = Field(default_factory=dict)


class _DecisionFields(StrictModel):
    thinking: str = Field(max_length=180)
    reflection: str | None = Field(max_length=160)
    goal_progress: str = Field(max_length=160)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class _ActDecision(_DecisionFields):
    decision: Literal["act"]
    action: _AgentAction


class _DoneDecision(_DecisionFields):
    decision: Literal["done"]
    action: None


class _StuckDecision(_DecisionFields):
    decision: Literal["stuck"]
    action: None


_AgentDecision = Annotated[
    _ActDecision | _DoneDecision | _StuckDecision,
    Field(discriminator="decision"),
]
_DECISION_ADAPTER = TypeAdapter(_AgentDecision)
_SCHEMA = _DECISION_ADAPTER.json_schema()


@dataclass(slots=True)
class _ActiveSkill:
    """A model-selected hard skill that the runtime has not finished yet.

    AerialClaw's upstream agent loop waits for one hard-skill result before the
    next LLM turn. SUPER is a receding-horizon planner, so a long ``goto`` may
    need several local replans. Those replans continue the *same* selected hard
    skill and must not be mistaken for new semantic decisions.
    """

    skill_name: str
    args: dict[str, float | str | bool]
    last_decision_id: str
    target: Vec3 | None = None
    tolerance_m: float = 1.0
    duration_s: float | None = None
    accepted_at_ns: int | None = None
    target_evidence_t_sim_ns: int | None = None


def _strip_json_wrapper(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    # Some reasoning models expose an XML thinking block despite JSON mode.
    text = re.sub(r"^<think>[\s\S]*?</think>\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _read_required(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AerialClawUnavailable(f"required AerialClaw document is unavailable: {path}") from exc
    if not text:
        raise AerialClawUnavailable(f"required AerialClaw document is empty: {path}")
    return text


@register("policy", "aerialclaw_agent")
class AerialClawAgentPolicy:
    """Incremental LLM agent over validated hard skills and Markdown strategies."""

    role = "policy"
    requires_real_inference = True
    """The generic cost-only backend is intentionally not an execution fallback."""

    def __init__(self, **params: Any) -> None:
        self.model_id = str(params.get("model_id", "gpt-oss:20b"))
        self.context_steps = int(params.get("context_steps", 6))
        self.validity_s = float(params.get("validity_s", 5.0))
        self.max_parse_attempts = int(params.get("max_parse_attempts", 2))
        self.temperature = float(params.get("temperature", 0.0))
        self.skill_allowlist = tuple(
            str(name)
            for name in params.get(
                "allowed_skills",
                ("goto", "hover", "scan", "stop"),
            )
        )
        self.target_label = str(params.get("target_label", "target"))
        docs = params.get("documents_dir")
        self.documents_dir = (
            Path(str(docs)) if docs else Path(__file__).with_name("aerialclaw_docs")
        )
        self.soul = _read_required(self.documents_dir / "SOUL.md")
        self.strategies = {
            "long_horizon_nav": _read_required(self.documents_dir / "navigate_target.md"),
            "object_search": _read_required(self.documents_dir / "search_target.md"),
            "failure_recovery": _read_required(self.documents_dir / "recover_route.md"),
        }
        self.services: RuntimeServices | None = None
        self._mission: MissionSpec | None = None
        self._history: list[dict[str, object]] = []
        self._last_decision_id: str | None = None
        self._last_prompt = ""
        self._last_raw = ""
        self._calls = 0
        self._parse_failures = 0
        self._protocol_rejections = 0
        self._terminal_decisions = 0
        self._home: Vec3 | None = None
        self._visited_positions: list[Vec3] = []
        self._active_skill: _ActiveSkill | None = None
        self._executor_replans = 0
        self._busy_cycles = 0
        self._scan_angle_since_motion_rad = 0.0
        self._scan_viewpoint: Vec3 | None = None
        self._home_yaw_rad: float | None = None
        self._coverage_points: list[tuple[int, Vec3]] = []

    @property
    def name(self) -> str:
        return "aerialclaw_agent"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("skill", "mission_directive")

    def bind_runtime(self, services: RuntimeServices) -> None:
        self.services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        del seed
        self._mission = mission
        self._history = []
        self._last_decision_id = None
        self._last_prompt = ""
        self._last_raw = ""
        self._calls = 0
        self._parse_failures = 0
        self._protocol_rejections = 0
        self._terminal_decisions = 0
        self._home = None
        self._visited_positions = []
        self._active_skill = None
        self._executor_replans = 0
        self._busy_cycles = 0
        self._scan_angle_since_motion_rad = 0.0
        self._scan_viewpoint = None
        self._home_yaw_rad = None
        self._coverage_points = []

    def stats(self) -> dict[str, float]:
        coverage_visited = 0
        if self._coverage_points:
            coverage_visited = sum(
                any(point.distance_to(previous) <= 6.0 for previous in self._visited_positions)
                for _, point in self._coverage_points
            )
        return {
            "aerialclaw_calls": float(self._calls),
            "aerialclaw_parse_failures": float(self._parse_failures),
            "aerialclaw_protocol_rejections": float(self._protocol_rejections),
            "aerialclaw_terminal_decisions": float(self._terminal_decisions),
            "aerialclaw_history_steps": float(len(self._history)),
            "aerialclaw_visited_positions": float(len(self._visited_positions)),
            "aerialclaw_coverage_candidates_visited": float(coverage_visited),
            "aerialclaw_executor_replans": float(self._executor_replans),
            "aerialclaw_busy_cycles": float(self._busy_cycles),
            "aerialclaw_scan_angle_since_motion_rad": self._scan_angle_since_motion_rad,
        }

    @property
    def last_prompt(self) -> str:
        """Inspectable for fidelity tests; never emitted into experimental logs."""

        return self._last_prompt

    def _runtime(self) -> tuple[RuntimeServices, object]:
        if self.services is None or self.services.inference is None:
            raise AerialClawUnavailable("AerialClaw requires a bound real inference backend")
        backend = self.services.inference
        # A cost-only simulated backend cannot execute this policy. Checking its
        # name first produces the scientifically relevant error even if its
        # accounting model id also differs.
        if getattr(backend, "name", "") in {"simulated", "free"}:
            raise AerialClawUnavailable(
                "AerialClaw requires model output; simulated/free inference is cost-only"
            )
        backend_model = getattr(backend, "model_id", self.model_id)
        if backend_model != self.model_id:
            raise AerialClawUnavailable(
                f"policy declares model {self.model_id!r}, backend serves {backend_model!r}"
            )
        return self.services, backend

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        services, backend = self._runtime()
        self._attach_runtime_feedback(ctx)
        continuation = self._continue_active_skill(ctx, services)
        if continuation is not False:
            return continuation
        prompt = self._build_prompt(ctx)
        self._last_prompt = prompt
        parsed: _AgentDecision | None = None
        errors: list[str] = []

        for attempt in range(self.max_parse_attempts):
            retry = ""
            if attempt:
                retry = (
                    "\n\nYour preceding reply was invalid: "
                    f"{errors[-1] if errors else 'schema mismatch'}. Return one object matching "
                    "the JSON schema and operating contract exactly; do not add prose or Markdown."
                )
            result = await backend.invoke(
                InferenceRequest(
                    model_id=self.model_id,
                    role=self.role,
                    prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    input_tokens=max(1, len(prompt) // 4),
                    observation_seq=ctx.observation.seq,
                    prompt=prompt + retry,
                    response_schema=_SCHEMA,
                )
            )
            self._calls += 1
            raw = str(result.payload or "")
            self._last_raw = raw
            if not raw.strip():
                self._parse_failures += 1
                errors.append("empty model output")
                continue
            try:
                parsed = _DECISION_ADAPTER.validate_python(json.loads(_strip_json_wrapper(raw)))
                failed_dispatches = sum(
                    1
                    for step in self._history
                    if isinstance(step.get("feedback"), dict)
                    and not bool(step["feedback"].get("dispatch_accepted"))  # type: ignore[union-attr]
                )
                if parsed.decision == "stuck" and failed_dispatches < 3:
                    self._protocol_rejections += 1
                    errors.append(
                        "stuck is forbidden before three validated dispatch failures; "
                        "choose an action"
                    )
                    parsed = None
                    continue
                if parsed.decision == "stuck" and self._unvisited_coverage_count(ctx) > 0:
                    self._protocol_rejections += 1
                    errors.append(
                        "stuck violates the active search soft skill while BODY-derived "
                        "coverage options remain unvisited; choose scan or goto"
                    )
                    parsed = None
                    continue
                if parsed.decision == "done" and not bool(
                    self._completion_evidence(ctx)["supported"]
                ):
                    self._protocol_rejections += 1
                    errors.append(
                        "done violates the terminal contract because BODY-derived mission "
                        "completion evidence is unsupported; choose decision act with scan "
                        "or an evidence-supported goto"
                    )
                    parsed = None
                    continue
                if (
                    parsed.decision == "act"
                    and parsed.action is not None
                    and parsed.action.skill not in self.skill_allowlist
                ):
                    self._protocol_rejections += 1
                    errors.append(
                        f"skill {parsed.action.skill!r} is outside BODY.md capability bounds"
                    )
                    parsed = None
                    continue
                if (
                    parsed.decision == "act"
                    and parsed.action is not None
                    and self._repeats_rejected_action(parsed.action)
                ):
                    self._protocol_rejections += 1
                    errors.append(
                        "the identical skill and arguments were just rejected by the "
                        "validated runtime; reflection requires a different skill or arguments"
                    )
                    parsed = None
                    continue
                if (
                    parsed.decision == "act"
                    and parsed.action is not None
                    and parsed.action.skill == "goto"
                    and bool(self._coverage_reference(ctx))
                    and self._scan_angle_since_motion_rad < math.tau
                    and self._unvisited_coverage_count(ctx) > 0
                    and not self._goto_has_target_evidence(parsed.action, ctx)
                ):
                    self._protocol_rejections += 1
                    errors.append(
                        "goto violates the active search soft skill because this viewpoint "
                        "has not completed one local scan and no exact-label target evidence "
                        "supports that goto; choose scan"
                    )
                    parsed = None
                    continue
                if (
                    parsed.decision == "act"
                    and parsed.action is not None
                    and parsed.action.skill == "scan"
                    and self._scan_angle_since_motion_rad >= math.tau
                    and self._unvisited_coverage_count(ctx) > 0
                ):
                    self._protocol_rejections += 1
                    errors.append(
                        "scan violates the active search soft skill because a full local "
                        "turn is already complete and unvisited coverage options remain; "
                        "choose goto"
                    )
                    parsed = None
                    continue
                break
            except (json.JSONDecodeError, ValidationError) as exc:
                self._parse_failures += 1
                detail = " ".join(str(exc).split())[:500]
                errors.append(f"{detail}; output={raw[:300]!r}")

        if parsed is None:
            raise AerialClawOutputError(
                f"model {self.model_id!r} produced no valid decision after "
                f"{self.max_parse_attempts} attempts: {'; '.join(errors)}"
            )

        now_ns = services.clock.now_ns()
        wall_ns = services.clock.wall_ns()
        decision_id = uuid.uuid4().hex[:12]
        if parsed.decision == "act":
            assert parsed.action is not None
            payload: SkillCall | MissionDirective = SkillCall(
                skill_name=parsed.action.skill,
                args=parsed.action.args,
            )
            kind = DecisionKind.SKILL
        elif parsed.decision == "done":
            # Done remains a bounded skill proposal so the common runtime can
            # validate its live semantic precondition. A hallucinated terminal
            # claim is fed back as a rejected skill rather than ending the run.
            self._terminal_decisions += 1
            payload = SkillCall(
                skill_name="stop",
                args={"reason": f"AerialClaw goal completed: {parsed.goal_progress}"},
            )
            kind = DecisionKind.SKILL
        else:
            self._terminal_decisions += 1
            payload = MissionDirective(
                label=ProgressLabel.STOP,
                rationale=f"AerialClaw agent stuck: {parsed.goal_progress}",
            )
            kind = DecisionKind.MISSION_DIRECTIVE

        self._history.append(
            {
                "decision_id": decision_id,
                "decision": parsed.decision,
                "skill": parsed.action.skill if parsed.action else None,
                "args": parsed.action.args if parsed.action else {},
                "reflection": parsed.reflection,
                "progress": parsed.goal_progress,
                "feedback": "pending",
            }
        )
        self._history = self._history[-max(1, self.context_steps) :]
        self._last_decision_id = decision_id
        if parsed.decision == "act" and parsed.action is not None:
            self._active_skill = self._make_active_skill(parsed.action, ctx, decision_id)
        return DecisionEnvelope(
            decision_id=decision_id,
            kind=kind,
            payload=payload,
            source_observation_seq=ctx.observation.seq,
            source_t_sim_ns=ctx.observation.t_sim_ns,
            produced_t_wall_ns=wall_ns,
            produced_t_sim_ns=now_ns,
            valid_until_t_sim_ns=now_ns + s_to_ns(self.validity_s),
            confidence=parsed.confidence,
            producer=self.name,
            provenance={
                "model_id": self.model_id,
                "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "agent_decision": parsed.decision,
            },
        )

    def _attach_runtime_feedback(self, ctx: DecisionContext) -> None:
        feedback = ctx.last_routing_feedback
        if feedback is None or feedback.decision_id != self._last_decision_id or not self._history:
            return
        self._history[-1]["feedback"] = {
            "dispatch_accepted": feedback.accepted,
            "dispatch_reason_not_completion": feedback.reason,
            "expanded_kind": feedback.expanded_kind.value if feedback.expanded_kind else None,
        }
        active = self._active_skill
        if active is None or feedback.decision_id != active.last_decision_id:
            return
        if feedback.accepted:
            active.accepted_at_ns = feedback.t_sim_ns
        else:
            # The official loop returns a failed hard-skill result to the LLM.
            # It may choose a different action on this same policy cycle.
            self._active_skill = None

    def _make_active_skill(
        self, action: _AgentAction, ctx: DecisionContext, decision_id: str
    ) -> _ActiveSkill | None:
        args = dict(action.args)
        if action.skill == "goto":
            numeric = (args.get("x"), args.get("y"), args.get("z"))
            if all(
                isinstance(value, (int, float)) and not isinstance(value, bool) for value in numeric
            ):
                return _ActiveSkill(
                    skill_name=action.skill,
                    args=args,
                    last_decision_id=decision_id,
                    target=Vec3(x=float(numeric[0]), y=float(numeric[1]), z=float(numeric[2])),
                    tolerance_m=float(args.get("tolerance_m", 1.0)),
                    target_evidence_t_sim_ns=self._target_evidence_timestamp(action, ctx),
                )
        if action.skill == "scan":
            return _ActiveSkill(
                skill_name=action.skill,
                args=args,
                last_decision_id=decision_id,
                duration_s=float(args.get("duration_s", 1.0)),
            )
        if action.skill == "hover":
            return _ActiveSkill(
                skill_name=action.skill,
                args=args,
                last_decision_id=decision_id,
                target=ctx.observation.position,
                tolerance_m=0.5,
            )
        return None

    def _continue_active_skill(
        self, ctx: DecisionContext, services: RuntimeServices
    ) -> DecisionEnvelope | Literal[False] | None:
        """Continue execution without inventing another semantic decision.

        ``False`` is the sentinel meaning the skill completed or failed and a
        fresh LLM cycle should run. ``None`` means a time-bounded skill is still
        executing. A returned envelope is a local replan of the exact same
        model-selected absolute goal.
        """

        active = self._active_skill
        if active is None:
            return False
        if active.accepted_at_ns is None:
            self._busy_cycles += 1
            return None

        if active.duration_s is not None:
            if ctx.t_sim_ns < active.accepted_at_ns + s_to_ns(active.duration_s):
                self._busy_cycles += 1
                return None
            self._mark_skill_complete(ctx, 0.0)
            return False

        if active.target is None:
            self._active_skill = None
            return False
        remaining = ctx.observation.position.distance_to(active.target)
        if remaining <= active.tolerance_m and ctx.observation.velocity.norm() <= 0.75:
            self._mark_skill_complete(ctx, remaining)
            return False

        decision_id = uuid.uuid4().hex[:12]
        now_ns = services.clock.now_ns()
        active.last_decision_id = decision_id
        active.accepted_at_ns = None
        self._last_decision_id = decision_id
        self._executor_replans += 1
        self._busy_cycles += 1
        if self._history:
            self._history[-1]["feedback"] = {
                "dispatch_accepted": True,
                "dispatch_reason_not_completion": "skill still executing; local replan",
                "skill_completed": False,
                "distance_remaining_m": round(remaining, 2),
            }
        return DecisionEnvelope(
            decision_id=decision_id,
            kind=DecisionKind.SKILL,
            payload=SkillCall(skill_name=active.skill_name, args=active.args),
            source_observation_seq=ctx.observation.seq,
            source_t_sim_ns=ctx.observation.t_sim_ns,
            produced_t_wall_ns=services.clock.wall_ns(),
            produced_t_sim_ns=now_ns,
            valid_until_t_sim_ns=now_ns + s_to_ns(self.validity_s),
            confidence=1.0,
            producer=f"{self.name}:skill_executor",
            provenance={
                "model_id": self.model_id,
                "agent_decision": "continue_selected_skill",
            },
        )

    def _mark_skill_complete(self, ctx: DecisionContext, remaining_m: float) -> None:
        active = self._active_skill
        if active is not None and active.skill_name == "scan":
            yaw_rate = active.args.get("yaw_rate_rps", 0.6)
            duration = active.args.get("duration_s", 1.0)
            if (
                isinstance(yaw_rate, (int, float))
                and not isinstance(yaw_rate, bool)
                and isinstance(duration, (int, float))
                and not isinstance(duration, bool)
            ):
                self._scan_angle_since_motion_rad += abs(float(yaw_rate)) * float(duration)
        elif active is not None and active.skill_name == "goto":
            self._scan_angle_since_motion_rad = 0.0
            if active.target is not None and active.target_evidence_t_sim_ns is not None:
                ctx.scratch["semantic_completion_evidence"] = SemanticCompletionEvidence(
                    label=self.target_label,
                    position=active.target,
                    observed_t_sim_ns=active.target_evidence_t_sim_ns,
                    completed_t_sim_ns=ctx.t_sim_ns,
                    source_decision_id=active.last_decision_id,
                )
        if self._history:
            self._history[-1]["feedback"] = {
                "dispatch_accepted": True,
                "dispatch_reason_not_completion": "hard skill completed",
                "skill_completed": True,
                "distance_remaining_m": round(remaining_m, 2),
                "completion_position_enu_m": [
                    round(ctx.observation.position.x, 2),
                    round(ctx.observation.position.y, 2),
                    round(ctx.observation.position.z, 2),
                ],
            }
        self._active_skill = None

    def _build_prompt(self, ctx: DecisionContext) -> str:
        mission = self._mission or ctx.mission
        self._record_position(ctx.observation.position, ctx.observation.yaw_rad)
        strategy = self.strategies.get(
            mission.task_family.value, self.strategies["long_horizon_nav"]
        )
        allowed = set(mission.allowed_skills)
        catalog = "\n".join(
            line
            for name, line in _HARD_SKILLS.items()
            if name in self.skill_allowlist and (not allowed or name in allowed)
        )
        detections = [
            {
                "label": d.label,
                "score": round(d.score, 3),
                "position_enu_m": [
                    round(d.position.x, 2),
                    round(d.position.y, 2),
                    round(d.position.z, 2),
                ]
                if d.position is not None
                else None,
                "distance_m": round(ctx.observation.position.distance_to(d.position), 2)
                if d.position is not None
                else None,
            }
            for d in ctx.perception.detections
        ]
        target_detections = [item for item in detections if item["label"] == self.target_label]
        other_detections = [item for item in detections if item["label"] != self.target_label]
        memories = [
            {
                "summary": item.summary,
                "label": item.label,
                "evidence_position_enu_m": (
                    [
                        round(item.position.x, 2),
                        round(item.position.y, 2),
                        round(item.position.z, 2),
                    ]
                    if item.position is not None
                    else None
                ),
                "distance_from_current_m": (
                    round(ctx.observation.position.distance_to(item.position), 2)
                    if item.position is not None
                    else None
                ),
                "age_s": round((ctx.t_sim_ns - item.t_sim_ns) / 1e9, 2),
            }
            for item in ctx.memory.items[-self.context_steps :]
        ]
        target_memories = [item for item in memories if item["label"] == self.target_label]
        other_memories = [item for item in memories if item["label"] != self.target_label]
        completion_evidence = self._completion_evidence(ctx)
        soft_skill_phase = self._soft_skill_phase(ctx, completion_evidence)
        body = {
            "frame": "ENU metres; z is altitude above ground",
            "position": [
                round(ctx.observation.position.x, 2),
                round(ctx.observation.position.y, 2),
                round(ctx.observation.position.z, 2),
            ],
            "velocity": [
                round(ctx.observation.velocity.x, 2),
                round(ctx.observation.velocity.y, 2),
                round(ctx.observation.velocity.z, 2),
            ],
            "yaw_rad": round(ctx.observation.yaw_rad, 3),
            "battery": round(ctx.observation.battery_frac, 3),
            "geofence_radius_m": mission.constraints.geofence_radius_m,
            "altitude_m": [mission.constraints.min_altitude_m, mission.constraints.max_altitude_m],
            "max_speed_mps": mission.constraints.max_speed_mps,
            "success_radius_m": mission.success.goal_radius_m,
            "scan_coverage_at_current_viewpoint_rad": round(self._scan_angle_since_motion_rad, 2),
            "full_local_scan_completed": self._scan_angle_since_motion_rad >= math.tau,
            "soft_skill_phase": soft_skill_phase,
        }
        coverage = self._coverage_reference(ctx)
        return f"""{self.soul}

## Operating contract
You are the semantic brain in a closed-loop aerial agent. Choose exactly ONE next hard skill.
The runtime, SUPER planner and controller execute it and report validation feedback next cycle.
Never invent detections or hidden target coordinates. Never output raw velocity or a trajectory.
If a call was rejected, change its arguments or skill. Do not claim done unless current sensor,
memory and position evidence show the mission is complete. Output JSON only.
API SEMANTICS: `decision: act` means execute ANY hard skill, including information-gathering
`scan`. For example, a safe search call is
{{"thinking":"target not visible, scan safely","decision":"act","action":
{{"skill":"scan","args":{{"yaw_rate_rps":1.5,"duration_s":5.0}}}},
"reflection":null,"goal_progress":"searching","confidence":0.8}}.
`decision: stuck` is irreversible terminal mission failure; it never means uncertain/searching.
IMPORTANT: accepted/planned dispatch feedback means only that execution started. It does NOT mean
the vehicle arrived. Prove arrival from the CURRENT BODY position, live target distance and speed.
Fresh bounded target memory may prove arrival after the target just leaves the field of view.
When BODY-derived mission completion evidence says `supported: true`, output `decision: done`
with `action: null` immediately; another goto or scan cannot improve a completed arrival.
`stuck` is permitted only after at least three validated dispatch failures and no safe skill
remains.

## Mission
{mission.instruction}
Task family: {mission.task_family.value}
Exact semantic target label: {self.target_label!r}
Success requires an explicit done decision while actually at the target.

## BODY.md (generated from the active testbed adapter)
{json.dumps(body, sort_keys=True)}

## BODY-derived mission completion evidence (sensor/memory only, never scoring truth)
{json.dumps(completion_evidence, sort_keys=True)}

## Active soft-skill phase (state-machine advice, not an executable command)
{soft_skill_phase!r}. Follow this phase when choosing the one model-authored hard skill.
`scan_current_viewpoint` permits `act/scan`; `choose_unvisited_coverage_goto` permits an
unvisited coverage `act/goto`; `approach_exact_label_target` permits an evidence-supported
`act/goto`; `complete_supported_arrival` requires `done`.

## Hard-skill catalog
{catalog}

## Relevant soft skill (strategy, not an executable program)
{strategy}

## BODY-derived coverage reference (options, not commands)
{json.dumps(coverage, sort_keys=True)}

Coverage `goto_args` are ABSOLUTE ENU coordinates. If you choose one, call `goto` with those
arguments. Never copy an absolute coverage coordinate into relative `move` dx/dy/dz. `move`
means a displacement from the current BODY position and repeated calls accumulate displacement.

## Current exact-label target candidates
{json.dumps(target_detections, sort_keys=True)}

## Current non-target detections (context only; never mission-completion evidence)
{json.dumps(other_detections, sort_keys=True)}

## Bounded exact-label target memory
{json.dumps(target_memories, ensure_ascii=True)}

## Bounded non-target memory (context only)
{json.dumps(other_memories, ensure_ascii=True)}

## Prior decisions, reflections and validated runtime feedback
{json.dumps(self._history[-self.context_steps :], sort_keys=True)}

Return one JSON object with: thinking, decision (act|done|stuck), action
({{skill,args}} or null), reflection, goal_progress, confidence.
Keep thinking, reflection and goal_progress to one short sentence each.
"""

    def _record_position(self, position: Vec3, yaw_rad: float | None = None) -> None:
        if self._home is None:
            self._home = position
        if self._home_yaw_rad is None and yaw_rad is not None:
            self._home_yaw_rad = yaw_rad
        if self._scan_viewpoint is None:
            self._scan_viewpoint = position
        elif position.distance_to(self._scan_viewpoint) > 4.0:
            # Scan coverage belongs to a physical observation point. A failed
            # local plan may still have moved the vehicle substantially, so a
            # reset cannot depend only on a clean goto completion callback.
            self._scan_viewpoint = position
            self._scan_angle_since_motion_rad = 0.0
        if not self._visited_positions or all(
            position.distance_to(previous) > 4.0 for previous in self._visited_positions
        ):
            self._visited_positions.append(position)

    def _coverage_reference(self, ctx: DecisionContext) -> list[dict[str, object]]:
        """Reusable geofence-relative observation options for the search soft skill.

        No candidate depends on a landmark, obstacle list or scoring truth. The
        model remains responsible for selecting and sequencing calls.
        """

        if self._home is None:
            return []
        home = self._home
        if ctx.mission.task_family.value == "object_search":
            count = 8
            radius = ctx.mission.constraints.geofence_radius_m * 0.47
        elif ctx.mission.task_family.value == "long_horizon_nav":
            # A small launch-relative reconnaissance ring breaks geometric
            # occlusion without pretending the semantic target is known. The
            # altitude change supplies the useful viewpoint; keeping the
            # horizontal displacement local leaves enough horizon for the
            # model-selected target approach and explicit terminal decision.
            count = 4
            radius = min(5.0, ctx.mission.constraints.geofence_radius_m * 0.1)
        else:
            return []
        desired_altitude = 15.0 if ctx.mission.task_family.value == "long_horizon_nav" else 8.0
        altitude = min(
            ctx.mission.constraints.max_altitude_m - 1.0,
            max(ctx.mission.constraints.min_altitude_m, desired_altitude),
        )
        if not self._coverage_points:
            for index in range(count):
                desired_angle = self._coverage_angle(index, count)
                # The options are BODY-derived, so make each launch-relative
                # sector geometrically executable when the local fan can prove
                # a clear alternative.  This is not target guidance: only
                # obstacle ranges are consulted, and the same option set is
                # frozen for the episode before the model selects among it.
                safe_angle = widest_free_bearing(
                    ctx.observation,
                    desired_angle,
                    required_clearance_m=radius + 2.5,
                    max_deflection_rad=math.pi / 4.0,
                    step_rad=math.pi / 12.0,
                )
                angle = safe_angle if safe_angle is not None else desired_angle
                self._coverage_points.append(
                    (
                        index,
                        Vec3(
                            x=home.x + radius * math.cos(angle),
                            y=home.y + radius * math.sin(angle),
                            z=altitude,
                        ),
                    )
                )
        candidates: list[dict[str, object]] = []
        for index, point in self._coverage_points:
            candidates.append(
                {
                    "id": index,
                    "position_enu_m": [round(point.x, 1), round(point.y, 1), round(point.z, 1)],
                    "goto_args": {
                        "x": round(point.x, 1),
                        "y": round(point.y, 1),
                        "z": round(point.z, 1),
                        "tolerance_m": 2.5,
                    },
                    "visited": any(
                        point.distance_to(previous) <= 6.0 for previous in self._visited_positions
                    ),
                }
            )
        return candidates

    def _coverage_angle(self, index: int, count: int) -> float:
        if self._mission is not None and self._mission.task_family.value == "long_horizon_nav":
            offsets = (0.0, math.pi / 2.0, -math.pi / 2.0, math.pi)
            return (self._home_yaw_rad or 0.0) + offsets[index]
        # Search coverage is also body-relative.  A world-axis ring would make
        # the first several slow semantic turns east/northeast on every map,
        # even when the observable launch attitude faces elsewhere.
        return (self._home_yaw_rad or 0.0) + index * math.tau / count

    def _completion_evidence(self, ctx: DecisionContext) -> dict[str, object]:
        radius = ctx.mission.success.goal_radius_m
        coordinate = public_coordinate_goal(ctx.mission)
        if coordinate is not None:
            distance = ctx.observation.position.distance_to(coordinate)
            speed = ctx.observation.velocity.norm()
            return {
                "supported": distance <= radius and speed <= 0.75,
                "source": "explicit public mission coordinate and current odometry",
                "target_distance_m": round(distance, 2),
                "target_position_enu_m": [coordinate.x, coordinate.y, coordinate.z],
                "evidence_age_s": 0.0,
                "vehicle_speed_mps": round(speed, 2),
                "required_radius_m": radius,
                "required_max_speed_mps": 0.75,
            }
        candidates: list[tuple[str, float, float]] = []
        for detection in ctx.perception.detections:
            if detection.label == self.target_label and detection.position is not None:
                candidates.append(
                    (
                        "live exact-label detection",
                        ctx.observation.position.distance_to(detection.position),
                        0.0,
                    )
                )
        for item in ctx.memory.items:
            if item.label != self.target_label or item.position is None:
                continue
            age_s = max(0.0, (ctx.t_sim_ns - item.t_sim_ns) / 1e9)
            if age_s <= 10.0:
                candidates.append(
                    (
                        "recent exact-label memory",
                        ctx.observation.position.distance_to(item.position),
                        age_s,
                    )
                )
        completed = ctx.scratch.get("semantic_completion_evidence")
        if (
            isinstance(completed, SemanticCompletionEvidence)
            and completed.label == self.target_label
        ):
            completed_age_s = max(0.0, (ctx.t_sim_ns - completed.completed_t_sim_ns) / 1e9)
            if completed_age_s <= 10.0:
                candidates.append(
                    (
                        "completed evidence-supported target skill",
                        ctx.observation.position.distance_to(completed.position),
                        completed_age_s,
                    )
                )
        best = min(candidates, key=lambda item: item[1], default=None)
        speed = ctx.observation.velocity.norm()
        supported = best is not None and best[1] <= radius and speed <= 0.75
        return {
            "supported": supported,
            "source": best[0] if best is not None else None,
            "target_distance_m": round(best[1], 2) if best is not None else None,
            "evidence_age_s": round(best[2], 2) if best is not None else None,
            "vehicle_speed_mps": round(speed, 2),
            "required_radius_m": radius,
            "required_max_speed_mps": 0.75,
        }

    def _unvisited_coverage_count(self, ctx: DecisionContext) -> int:
        return sum(not bool(candidate["visited"]) for candidate in self._coverage_reference(ctx))

    def _soft_skill_phase(self, ctx: DecisionContext, completion: dict[str, object]) -> str:
        if bool(completion["supported"]):
            return "complete_supported_arrival"
        target_supported = any(
            detection.label == self.target_label and detection.position is not None
            for detection in ctx.perception.detections
        ) or any(
            item.label == self.target_label
            and item.position is not None
            and ctx.t_sim_ns - item.t_sim_ns <= s_to_ns(10.0)
            for item in ctx.memory.items
        )
        if target_supported:
            return "approach_exact_label_target"
        if self._scan_angle_since_motion_rad < math.tau:
            return "scan_current_viewpoint"
        if self._unvisited_coverage_count(ctx) > 0:
            return "choose_unvisited_coverage_goto"
        return "search_evidence_exhausted"

    def _goto_has_target_evidence(self, action: _AgentAction, ctx: DecisionContext) -> bool:
        return self._target_evidence_timestamp(action, ctx) is not None

    def _repeats_rejected_action(self, action: _AgentAction) -> bool:
        if not self._history:
            return False
        previous = self._history[-1]
        feedback = previous.get("feedback")
        return (
            isinstance(feedback, dict)
            and feedback.get("dispatch_accepted") is False
            and previous.get("skill") == action.skill
            and previous.get("args") == action.args
        )

    def _target_evidence_timestamp(self, action: _AgentAction, ctx: DecisionContext) -> int | None:
        values = (action.args.get("x"), action.args.get("y"), action.args.get("z"))
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
        ):
            return None
        proposed = Vec3(x=float(values[0]), y=float(values[1]), z=float(values[2]))
        if any(
            detection.label == self.target_label
            and detection.position is not None
            and proposed.distance_to(detection.position) <= 3.0
            for detection in ctx.perception.detections
        ):
            return ctx.t_sim_ns
        timestamps = [
            item.t_sim_ns
            for item in ctx.memory.items
            if item.label == self.target_label
            and item.position is not None
            and ctx.t_sim_ns - item.t_sim_ns <= s_to_ns(10.0)
            and proposed.distance_to(item.position) <= 3.0
        ]
        return max(timestamps, default=None)


_HARD_SKILLS = {
    "goto": (
        '- goto: fly via shared SUPER to absolute ENU {"x":number,"y":number,"z":number,'
        '"label"?:string,"tolerance_m"?:number}'
    ),
    "move": (
        '- move: relative displacement {"dx"?:number,"dy"?:number,"dz"?:number,'
        '"tolerance_m"?:number}; at least one delta non-zero'
    ),
    "hover": "- hover: hold position; args must be {}",
    "scan": '- scan: rotate in place {"yaw_rate_rps"?:number 0.05..2.0,"duration_s"?:number <=10}',
    "back_off": '- back_off: retreat from current heading {"distance_m"?:positive number}',
    "ascend": '- ascend: climb vertically {"dz"?:positive number}',
    "stop": (
        '- stop: request mission termination {"reason"?:string}; use only when actually complete'
    ),
}
