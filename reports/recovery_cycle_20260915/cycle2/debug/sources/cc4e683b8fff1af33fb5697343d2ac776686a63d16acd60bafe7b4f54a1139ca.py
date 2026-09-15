"""Named VLM-selected observed-view return variant; not the OnFly paper mechanism.

The model chooses whether to return. Stored onboard pose/heading defines that
option; normal verification/planning executes it, with one bounded attempt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from uavlab.contracts import DecisionKind, ProgressLabel, Vec3, WaypointGoal, s_to_ns
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.interfaces import InferenceRequest
from uavlab.plugins.reasoning.onfly import (
    OnFlyDecisionAgent,
    OnFlySemanticGeometricVerifier,
    _encode_png,
    _extract_json,
)
from uavlab.plugins.verifier.bounds import SemanticGeometricVerifier

AUTH = 'observed_view_return_authorizations'


@dataclass(frozen=True)
class ObservedView:
    position: Vec3
    yaw: float
    seq: int
    t_ns: int
    image: Any


@register('policy', 'vlm_observed_view_return')
class ObservedViewPolicy(OnFlyDecisionAgent):
    def __init__(self, **params):
        super().__init__(**params)
        self.return_timeout_s = float(params.get('return_timeout_s', 20.0))
        self.anchor_max_age_s = float(params.get('anchor_max_age_s', 30.0))
        self.return_tolerance_m = float(params.get('return_tolerance_m', 0.25))
        if not all(math.isfinite(v) and v > 0 for v in (
            self.return_timeout_s, self.anchor_max_age_s, self.return_tolerance_m)):
            raise ValueError('Observed-view return bounds must be finite and positive')
        self.anchor = None
        self.active = None
        self.deadline_ns = 0
        self.return_requests = 0
        self.return_outcome = 'not_requested'
        self.last_return_decision = None

    @property
    def name(self):
        return 'vlm_observed_view_return'

    def reset(self, mission, seed):
        super().reset(mission, seed)
        self.anchor = self.active = None
        self.deadline_ns = 0
        self.return_requests = 0
        self.return_outcome = 'not_requested'
        self.last_return_decision = None

    def _goal(self, ctx, view, phase):
        goal = WaypointGoal(target=view.position, view_yaw_rad=view.yaw,
                            tolerance_m=self.return_tolerance_m, stop_at_target=False)
        envelope = self.envelope(ctx, DecisionKind.WAYPOINT, goal, 1.0,
                                note='Bounded onboard observed-view option', extra={
                                    'waypoint_kind': 'observed_view_return',
                                    'observed_view_phase': phase,
                                    'anchor_observation_seq': str(view.seq),
                                    'return_outcome': self.return_outcome,
                                })
        auth = ctx.scratch.setdefault(AUTH, {})
        # Trusted option binding, never a model-provided world position.
        auth[envelope.decision_id] = (goal, envelope.source_observation_seq,
                                      ctx.t_sim_ns + s_to_ns(3.0))
        for old in list(auth):
            if auth[old][2] < ctx.t_sim_ns:
                del auth[old]
        self.last_return_decision = envelope.decision_id
        return envelope

    def _hold(self, ctx, phase):
        return self._goal(ctx, ObservedView(ctx.observation.position,
                          ctx.observation.yaw_rad, ctx.observation.seq,
                          ctx.observation.t_sim_ns, None), phase)

    async def decide(self, ctx):
        if self.active is not None:
            feedback = ctx.last_routing_feedback
            blocked = (feedback is not None and not feedback.accepted
                       and feedback.decision_id == self.last_return_decision
                       and not feedback.reason.startswith('fresh observation required after'))
            error = math.atan2(math.sin(self.active.yaw - ctx.observation.yaw_rad),
                               math.cos(self.active.yaw - ctx.observation.yaw_rad))
            arrived = (ctx.observation.position.distance_to(self.active.position)
                       <= self.return_tolerance_m and abs(error) <= math.radians(5))
            if blocked or ctx.t_sim_ns >= self.deadline_ns or arrived:
                self.return_outcome = ('blocked' if blocked else 'expired'
                                       if ctx.t_sim_ns >= self.deadline_ns else 'view_restored')
                self.active = None
                self._previous_goal = None
                # One fresh policy observation after this hold decides what to do next.
                return self._hold(ctx, self.return_outcome)
            return self._goal(ctx, self.active, 'returning')

        lost = ctx.last_progress is not None and ctx.last_progress.label is ProgressLabel.LOST
        recent = (self.anchor is not None and
                  ctx.t_sim_ns - self.anchor.t_ns <= s_to_ns(self.anchor_max_age_s))
        if lost and recent and self.return_requests == 0:
            self.return_requests += 1
            current = global_store().get(ctx.observation.rgb.uri)
            delta = [getattr(ctx.observation.position, k)-getattr(self.anchor.position, k)
                     for k in ('x', 'y', 'z')]
            prompt = (
                f'Mission: {ctx.mission.instruction}. Image 1 is the historical view where '
                'the policy last identified the target. Image 2 is CURRENT. Historical '
                'visibility is not current visibility. The monitor reports LOST. '
                f'Onboard displacement east,north,up metres is {[round(v,2) for v in delta]}; '
                f'yaw change is '
                f'{math.degrees(ctx.observation.yaw_rad-self.anchor.yaw):.1f} degrees. '
                'Choose action=backtrack to request a verified return to the stored camera '
                'position AND heading; action=continue to keep choosing current-image points; '
                'or action=hold to wait. A return can be rejected by geometry and is allowed '
                'only once. Do not assume hidden passages are clear. Return only JSON with '
                'evidence describing current visibility and action. No coordinates or controls.'
            )
            schema = dict(type='object', properties={
                'evidence': dict(type='string', maxLength=160),
                'action': dict(type='string', enum=['backtrack', 'continue', 'hold'])},
                required=['evidence', 'action'], additionalProperties=False)
            result = await self.services.inference.invoke(InferenceRequest(
                model_id=self.model_id, role='policy', prompt_hash='observed_view_return:v1',
                input_tokens=max(1,len(prompt)//4), image_count=2,
                observation_seq=ctx.observation.seq, prompt=prompt,
                images=(_encode_png(self.anchor.image), _encode_png(current)),
                response_schema=schema))
            answer = _extract_json(result.payload)
            if (set(answer) != {'evidence','action'} or
                answer['action'] not in ['backtrack','continue','hold'] or
                    not isinstance(answer['evidence'],str)):
                raise RuntimeError('Invalid observed-view action')
            self.return_outcome = answer['action']
            if answer['action'] == 'backtrack':
                self.active = self.anchor
                self.deadline_ns = ctx.t_sim_ns + s_to_ns(self.return_timeout_s)
                return self._goal(ctx, self.active, 'selected')
            return self._hold(ctx, answer['action'])

        # Keep exact synchronized pixels/pose before any asynchronous inference.
        obs = ctx.observation
        image = global_store().get(obs.rgb.uri).copy()
        result = await super().decide(ctx)
        if result.provenance.get('waypoint_kind') == 'target':
            self.anchor = ObservedView(obs.position, obs.yaw_rad, obs.seq, obs.t_sim_ns, image)
        return result

    def stats(self):
        return {**super().stats(), 'observed_view_return_requests': float(self.return_requests),
                'observed_view_restored': float(self.return_outcome == 'view_restored')}


@register('verifier', 'observed_view_return')
class ObservedViewVerifier(OnFlySemanticGeometricVerifier):
    def __init__(self, **params):
        super().__init__(**params)
        self.return_verifier = SemanticGeometricVerifier(**{**params, 'repair': False})

    @property
    def name(self):
        return 'observed_view_return'

    def reset(self, mission, seed):
        super().reset(mission, seed)
        self.return_verifier.reset(mission, seed)

    def verify(self, envelope, ctx):
        if envelope.provenance.get('waypoint_kind') != 'observed_view_return':
            return super().verify(envelope, ctx)
        auth = ctx.scratch.get(AUTH, {}).get(envelope.decision_id)
        if (auth is None or auth[0] != envelope.payload or
                auth[1] != envelope.source_observation_seq or ctx.t_sim_ns > auth[2]):
            return self._reject('Observed-view goal has no valid onboard option binding')
        return self.return_verifier.verify(envelope, ctx)
