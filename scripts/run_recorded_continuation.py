"""Reconstruct a recorded flight, then optionally continue with local inference.

A diagnostic harness only: production policy/planner/controller are unchanged.
Every cached request and every prefix control is checked before proceeding.
"""

import argparse
import asyncio
import base64
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.experiments.manifest import build_manifest, write_manifest

SOURCE = Path("runs/c5_target_commitment_20260915_s1061")
REPORT = Path("reports/continuation_20260916")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def check_request(request, saved, source, now):
    fields = asdict(request)
    images = fields.pop("images")
    for key, value in fields.items():
        assert value == saved[key], f"request mismatch {saved['id']}: {key}"
    assert now == saved["started_t_sim_ns"], f"request time mismatch {saved['id']}"
    assert len(images) == len(saved["image_files"])
    for image, filename in zip(images, saved["image_files"], strict=True):
        assert base64.b64decode(image) == (source / filename).read_bytes(), (
            f"image mismatch {saved['id']}: {filename}"
        )


def payload_clean(value):
    if isinstance(value, dict):
        return {
            k: payload_clean(v)
            for k, v in value.items()
            if k not in {"_debug_source", "target_commitment_source_id", "source_decision_id"}
        }
    if isinstance(value, list):
        return [payload_clean(x) for x in value]
    return value


class Continuation(Orchestrator):
    def __init__(self, *args, live=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.live = live
        self.saved_calls = [read(p) for p in sorted((SOURCE / "debug/calls").glob("*.json"))]
        self.saved_events = [
            json.loads(x)
            for x in (SOURCE / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.prefix_types = {"control", "plan", "memory_update", "monitor", "verifier"}
        self.expected = {
            kind: [e for e in self.saved_events if e["event_type"] == kind]
            for kind in self.prefix_types
        }
        self.matched = dict.fromkeys(self.prefix_types, 0)
        self.requests = []
        self.fresh_requests = 0
        self.next_reply = None

    def _build_components(self):
        super()._build_components()
        backend = self.inference.backend
        original_invoke = backend.invoke
        original_post = backend._post
        original_emit = self.log.emit

        def emit(component, event_type, t_sim_ns, t_wall_ns, payload=None, trace_id=None):
            kind = event_type.value
            if kind in self.expected and t_sim_ns < 90_000_000_000:
                index = self.matched[kind]
                expected = self.expected[kind][index]
                assert t_sim_ns == expected["t_sim_ns"], f"{kind} time mismatch {index}"
                assert payload_clean(payload) == payload_clean(expected["payload"]), (
                    f"{kind} payload mismatch {index} at {t_sim_ns}"
                )
                self.matched[kind] += 1
            return original_emit(component, event_type, t_sim_ns, t_wall_ns, payload, trace_id)

        def post(path, body, _retry=True):
            if self.next_reply is not None:
                reply = self.next_reply
                self.next_reply = None
                return reply
            assert self.live and self.clock.now_ns() >= 89_000_000_000
            assert self.fresh_requests <= 47, "bounded continuation request limit exceeded"
            return original_post(path, body, _retry)

        async def invoke(request):
            index = len(self.requests)
            cached = index < 134
            now = self.clock.now_ns()
            if index < len(self.saved_calls):
                saved = self.saved_calls[index]
                check_request(request, saved, SOURCE, now)
                if cached:
                    assert saved["status"] == "complete"
                else:
                    assert saved["status"] == "cancelled" and index == 134
            elif not self.live:
                raise AssertionError("unexpected request in dry replay")
            if cached or not self.live:
                self.next_reply = {
                    "message": {"thinking": saved.get("response", "{}"), "content": ""},
                    "eval_count": saved.get("output_tokens", 0),
                }
            else:
                self.fresh_requests += 1
            row = dict(
                index=index + 1,
                role=request.role,
                observation_seq=request.observation_seq,
                started_s=now / 1e9,
                cached=cached,
                boundary_dummy=not self.live and index == 134,
                original_request_matched=index < len(self.saved_calls),
            )
            self.requests.append(row)
            write(self.out_dir / "CONTINUATION_AUDIT.json", self.audit())
            result = await original_invoke(request)
            row["completed_s"] = self.clock.now_ns() / 1e9
            return replace(result, cache_hit=cached)

        self.log.emit = emit
        backend._post = post
        backend.invoke = invoke

    def audit(self):
        return dict(
            source=str(SOURCE),
            live=self.live,
            matched=self.matched,
            cached_requests=sum(r["cached"] for r in self.requests),
            fresh_requests=self.fresh_requests,
            requests=self.requests,
            warning="Prefix inference metrics describe cache playback, not new model compute.",
        )


async def main(args):
    manifest = read(SOURCE / "manifest.json")
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    env_data = manifest["environment_config"]
    if args.live:
        proof = read(REPORT / "DRY_REPLAY.json")
        assert proof["passed"] and proof["matched"]["control"] == 1800
        assert proof["script_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        env_data["max_episode_s"] = 120.0
        env_data["params"]["success"]["max_flight_time_s"] = 120.0
    env = EnvironmentConfig.model_validate(env_data)
    assert arch.inference.params["host"] == "http://127.0.0.1:11435"
    assert arch.inference.params["charge_mode"] == "fixed"
    name = (
        "c5_commitment_continued_20260916_s1061"
        if args.live
        else "c5_commitment_replay_20260916_s1061"
    )
    out = Path("runs") / name
    assert not out.exists(), f"output already exists: {out}"
    write_manifest(build_manifest(arch, env, seeds=[1061]), out)
    runner = Continuation(
        arch,
        env,
        EpisodeSpec(episode_id=name, seed=1061),
        out_dir=out,
        debug_capture=True,
        live=args.live,
    )
    result = await runner.run()
    write(out / "result.json", result.model_dump(mode="json"))
    audit = runner.audit()
    audit["error"] = result.error
    audit["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    audit["passed"] = result.error is None and all(
        runner.matched[k] == len(v) for k, v in runner.expected.items()
    )
    write(out / "CONTINUATION_AUDIT.json", audit)
    write(REPORT / ("LIVE_REPLAY.json" if args.live else "DRY_REPLAY.json"), audit)
    print(
        json.dumps(
            dict(
                passed=audit["passed"],
                matched=audit["matched"],
                result=result.model_dump(mode="json"),
            ),
            indent=2,
        )
    )
    assert audit["passed"], audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    asyncio.run(main(parser.parse_args()))
