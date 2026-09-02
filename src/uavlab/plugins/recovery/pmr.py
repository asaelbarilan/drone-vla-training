"""PMR-style constrained recovery-skill reasoner.

The learned CVI decides whether to call this component. A real text model then
selects one symbolic recovery operation. It cannot emit coordinates, velocities,
or flight commands; local code grounds the option into typed shared skills.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator

from uavlab.contracts import (
    DecisionEnvelope,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    RecoveryRequest,
    SkillCall,
    StrictModel,
    Vec3,
    s_to_ns,
)
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.base import recall_target


class PMRUnavailable(RuntimeError):
    """The declared real reasoner or runtime service is unavailable."""


DecisionName = Literal[
    "local_continue",
    "goal_resume",
    "goal_alignment",
    "local_repair",
    "safe_hold_verify",
    "terminal_homing",
    "fallback_safe",
    "abort_if_unsafe",
]
OptionName = Literal[
    "continue",
    "resume_target",
    "scan_left",
    "scan_right",
    "back_off",
    "ascend",
    "hold",
    "approach_target",
    "abort",
]

_COMPATIBLE_OPTIONS: dict[str, frozenset[str]] = {
    "local_continue": frozenset({"continue"}),
    "goal_resume": frozenset({"resume_target", "approach_target"}),
    "goal_alignment": frozenset({"scan_left", "scan_right"}),
    "local_repair": frozenset({"back_off", "ascend", "scan_left", "scan_right"}),
    "safe_hold_verify": frozenset({"hold", "scan_left", "scan_right"}),
    "terminal_homing": frozenset({"approach_target", "resume_target"}),
    "fallback_safe": frozenset({"hold"}),
    "abort_if_unsafe": frozenset({"abort"}),
}


class _PMRDecision(StrictModel):
    decision: DecisionName
    reason: str = Field(min_length=1, max_length=180)
    suggested_option: OptionName
    risk: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _decision_matches_option(self) -> _PMRDecision:
        if self.suggested_option not in _COMPATIBLE_OPTIONS[self.decision]:
            raise ValueError(
                f"option {self.suggested_option!r} is incompatible with "
                f"decision {self.decision!r}"
            )
        return self


_SCHEMA = _PMRDecision.model_json_schema()


def _strip_json_wrapper(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^<think>[\s\S]*?</think>\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


@register("recovery", "pmr_recovery_reasoner")
class PMRRecoveryReasoner:
    """Real-model PMR reasoner restricted to predefined semantic skills."""

    role = "reasoner"
    requires_real_inference = True

    def __init__(self, **params: Any) -> None:
        self.model_id = str(params.get("model_id", "gpt-oss:20b"))
        self.target_label = str(params.get("target_label", "target"))
        self.max_parse_attempts = int(params.get("max_parse_attempts", 2))
        self.validity_s = float(params.get("validity_s", 15.0))
        self.services: RuntimeServices | None = None
        self._calls = 0
        self._parse_failures = 0
        self._protocol_rejections = 0
        self._backend_failures = 0
        self._fallbacks = 0
        self._decisions: dict[str, int] = {}
        self._last_prompt = ""

    @property
    def name(self) -> str:
        return "pmr_recovery_reasoner"

    @property
    def last_prompt(self) -> str:
        """Inspectable in tests; never copied into experimental logs."""
        return self._last_prompt

    def bind_runtime(self, services: RuntimeServices) -> None:
        self.services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        del mission, seed
        self._calls = 0
        self._parse_failures = 0
        self._protocol_rejections = 0
        self._backend_failures = 0
        self._fallbacks = 0
        self._decisions = {}
        self._last_prompt = ""

    def _runtime(self) -> tuple[RuntimeServices, object]:
        if self.services is None or self.services.inference is None:
            raise PMRUnavailable("PMR requires a bound real inference backend")
        backend = self.services.inference
        route_name = getattr(backend, "backend_name_for_role", None)
        effective_name = (
            str(route_name(self.role))
            if callable(route_name)
            else str(getattr(backend, "name", ""))
        )
        if effective_name in {"simulated", "free"}:
            raise PMRUnavailable(
                "PMR recovery requires model output; simulated/free inference is cost-only"
            )
        route_model = getattr(backend, "model_for_role", None)
        backend_model = (
            str(route_model(self.role))
            if callable(route_model)
            else str(getattr(backend, "model_id", self.model_id))
        )
        if backend_model != self.model_id:
            raise PMRUnavailable(
                f"recovery declares model {self.model_id!r}, backend serves {backend_model!r}"
            )
        return self.services, backend

    async def recover(
        self, request: RecoveryRequest, ctx: DecisionContext
    ) -> DecisionEnvelope | None:
        services, backend = self._runtime()
        prompt = self._build_prompt(request, ctx)
        self._last_prompt = prompt
        parsed: _PMRDecision | None = None
        errors: list[str] = []

        for attempt in range(self.max_parse_attempts):
            retry = ""
            if attempt:
                retry = (
                    "\n\nThe previous response violated the schema or recovery contract: "
                    f"{errors[-1]}. Return exactly one valid JSON object, with no prose."
                )
            try:
                result = await backend.invoke(  # type: ignore[attr-defined]
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
            except Exception as exc:
                self._backend_failures += 1
                errors.append(f"backend failure: {type(exc).__name__}")
                break
            self._calls += 1
            raw = str(result.payload or "")
            try:
                parsed = _PMRDecision.model_validate(json.loads(_strip_json_wrapper(raw)))
                break
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                self._parse_failures += 1
                self._protocol_rejections += 1
                errors.append(" ".join(str(exc).split())[:400])

        if parsed is None:
            self._fallbacks += 1
            return self._envelope(
                payload=self._safe_fallback(request),
                ctx=ctx,
                services=services,
                confidence=0.0,
                provenance={
                    "model_id": self.model_id,
                    "agent_decision": "local_fallback",
                    "suggested_option": "hold",
                    "trigger": request.trigger.name,
                },
            )

        payload = self._ground(parsed, request, ctx)
        self._decisions[parsed.decision] = self._decisions.get(parsed.decision, 0) + 1
        return self._envelope(
            payload=payload,
            ctx=ctx,
            services=services,
            confidence=parsed.confidence,
            provenance={
                "model_id": self.model_id,
                "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "agent_decision": parsed.decision,
                "suggested_option": parsed.suggested_option,
                "risk": parsed.risk,
                "trigger": request.trigger.name,
            },
        )

    def _build_prompt(self, request: RecoveryRequest, ctx: DecisionContext) -> str:
        obs = ctx.observation
        geometry = ctx.perception.geometry
        clearance = geometry.free_radius_m if geometry is not None else None
        progress = ctx.last_progress
        feedback = ctx.last_routing_feedback
        detections = sorted(
            ctx.perception.detections, key=lambda item: item.score, reverse=True
        )[:6]
        detection_text = ", ".join(
            f"{item.label}(score={item.score:.2f},distance="
            f"{item.distance_m if item.distance_m is not None else 'unknown'})"
            for item in detections
        ) or "none"
        option_text = ", ".join(
            f"{decision}=>{sorted(options)}"
            for decision, options in _COMPATIBLE_OPTIONS.items()
        )
        semantics = (
            "local_continue: nominal state and the validated local plan remains useful; "
            "goal_resume: target evidence exists but progress stalled, so resume or approach it; "
            "goal_alignment: target is lost or ambiguous, so reacquire it by scanning; "
            "local_repair: geometry or the planner is blocked, so back off, ascend, or scan; "
            "safe_hold_verify: an immediate uncertain hazard requires a brief hold or scan; "
            "terminal_homing: reliable nearby target evidence supports final approach; "
            "fallback_safe: no situation-specific recovery is supportable; "
            "abort_if_unsafe: only an imminent unrecoverable safety condition justifies stopping"
        )
        return (
            "You are PMR's selectively invoked UAV recovery reasoner. Choose one predefined "
            "semantic recovery operation. You have no motor authority. Never output coordinates, "
            "distances to fly, velocities, yaw rates, trajectories, code, or flight commands; "
            "local verified skills ground your symbolic choice. Return only the requested JSON.\n"
            f"Mission: {ctx.mission.instruction}\n"
            f"Trigger: {request.trigger.name}; cause={request.trigger.cause}; "
            f"call={request.call_index}; allowed_skills={list(request.allowed_skills)}\n"
            f"Runtime summary: {request.state_summary[:512] or 'none'}\n"
            f"Vehicle sensor state: position=({obs.position.x:.1f},{obs.position.y:.1f},"
            f"{obs.position.z:.1f}); speed={obs.velocity.norm():.2f}; yaw={obs.yaw_rad:.2f}; "
            f"battery={obs.battery_frac:.2f}; free_radius={clearance}\n"
            f"Progress: label={progress.label.value if progress else 'unknown'}; "
            f"stalled_s={progress.stalled_for_s if progress else 0.0:.1f}; "
            f"evidence={progress.evidence[:160] if progress else 'none'}\n"
            f"Current detections: {detection_text}\n"
            f"Last routing result: accepted={feedback.accepted if feedback else 'unknown'}; "
            f"reason={feedback.reason[:160] if feedback else 'none'}\n"
            f"Recovery semantics: {semantics}\n"
            f"Decision-option contract: {option_text}\n"
            "Required fields: decision, reason, suggested_option, risk, confidence."
        )

    def _ground(
        self, decision: _PMRDecision, request: RecoveryRequest, ctx: DecisionContext
    ) -> SkillCall | MissionDirective:
        option = decision.suggested_option
        if option == "continue":
            return MissionDirective(
                label=ProgressLabel.CONTINUE,
                subgoal="resume nominal local policy",
                rationale="PMR selected local_continue",
            )
        if option == "abort":
            return MissionDirective(
                label=ProgressLabel.STOP,
                subgoal="terminate safely",
                rationale="PMR selected abort_if_unsafe",
            )
        if option == "hold":
            return self._allowed_skill("hover", {}, request)
        if option in {"scan_left", "scan_right"}:
            yaw = 0.8 if option == "scan_left" else -0.8
            return self._allowed_skill(
                "scan", {"yaw_rate_rps": yaw, "duration_s": 1.5}, request
            )
        if option == "back_off":
            return self._allowed_skill("back_off", {"distance_m": 3.0}, request)
        if option == "ascend":
            return self._allowed_skill("ascend", {"dz": 2.0}, request)
        if option == "approach_target" and any(
            item.label == self.target_label and item.position is not None
            for item in ctx.perception.detections
        ):
            return self._allowed_skill(
                "approach",
                {"label": self.target_label, "standoff_m": 1.0, "tolerance_m": 0.8},
                request,
            )
        target = self._target(ctx)
        if target is not None:
            return self._allowed_skill(
                "goto",
                {
                    "x": target.x,
                    "y": target.y,
                    "z": target.z,
                    "label": self.target_label,
                    "tolerance_m": 1.0,
                },
                request,
            )
        return self._safe_fallback(request)

    def _target(self, ctx: DecisionContext) -> Vec3 | None:
        detected = max(
            (
                item
                for item in ctx.perception.detections
                if item.label == self.target_label and item.position is not None
            ),
            key=lambda item: item.score,
            default=None,
        )
        if detected is not None:
            return detected.position
        remembered = recall_target(ctx, self.target_label)
        return remembered.position if remembered is not None else None

    def _allowed_skill(
        self, name: str, args: dict[str, float | str | bool], request: RecoveryRequest
    ) -> SkillCall | MissionDirective:
        if request.allowed_skills and name not in request.allowed_skills:
            self._fallbacks += 1
            return self._safe_fallback(request)
        return SkillCall(skill_name=name, args=args)

    def _safe_fallback(self, request: RecoveryRequest) -> SkillCall | MissionDirective:
        if not request.allowed_skills or "hover" in request.allowed_skills:
            return SkillCall(skill_name="hover")
        return MissionDirective(
            label=ProgressLabel.CONTINUE,
            subgoal="retain current validated local policy",
            rationale="PMR local fallback; no safe recovery skill available",
        )

    def _envelope(
        self,
        *,
        payload: SkillCall | MissionDirective,
        ctx: DecisionContext,
        services: RuntimeServices,
        confidence: float,
        provenance: dict[str, str],
    ) -> DecisionEnvelope:
        now_ns = services.clock.now_ns()
        return DecisionEnvelope(
            decision_id=uuid.uuid4().hex[:12],
            kind=payload.kind,
            payload=payload,
            source_observation_seq=ctx.observation.seq,
            source_t_sim_ns=ctx.observation.t_sim_ns,
            produced_t_wall_ns=services.clock.wall_ns(),
            produced_t_sim_ns=now_ns,
            valid_until_t_sim_ns=now_ns + s_to_ns(self.validity_s),
            confidence=confidence,
            producer=self.name,
            provenance=provenance,
        )

    def stats(self) -> dict[str, float]:
        stats = {
            "pmr_reasoner_calls": float(self._calls),
            "pmr_reasoner_parse_failures": float(self._parse_failures),
            "pmr_reasoner_protocol_rejections": float(self._protocol_rejections),
            "pmr_reasoner_backend_failures": float(self._backend_failures),
            "pmr_reasoner_fallbacks": float(self._fallbacks),
        }
        for decision, count in self._decisions.items():
            stats[f"pmr_reasoner_decision_{decision}"] = float(count)
        return stats
