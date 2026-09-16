"""Reject changed evidence before a recorded-flight continuation."""

import base64
from dataclasses import asdict, replace

import pytest
from scripts.run_recorded_continuation import check_request, payload_clean

from uavlab.interfaces import InferenceRequest


def fixture(tmp_path):
    raw = b"exact source image"
    (tmp_path / "image.png").write_bytes(raw)
    req = InferenceRequest(
        model_id="qwen3-vl:4b",
        role="policy",
        prompt_hash="p",
        observation_seq=833,
        prompt="original",
        image_count=1,
        images=(base64.b64encode(raw).decode(),),
        response_schema={"type": "object"},
    )
    saved = asdict(req)
    saved.pop("images")
    saved.update(id="call", image_files=["image.png"], started_t_sim_ns=10)
    return req, saved


def test_exact_request(tmp_path):
    req, saved = fixture(tmp_path)
    check_request(req, saved, tmp_path, 10)


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt", "changed"),
        ("model_id", "different"),
        ("observation_seq", 834),
        ("response_schema", {"type": "string"}),
        ("images", (base64.b64encode(b"changed pixels").decode(),)),
    ],
)
def test_changed_request_is_rejected(tmp_path, field, value):
    req, saved = fixture(tmp_path)
    with pytest.raises(AssertionError):
        check_request(replace(req, **{field: value}), saved, tmp_path, 10)


def test_shifted_request_is_rejected(tmp_path):
    req, saved = fixture(tmp_path)
    with pytest.raises(AssertionError):
        check_request(req, saved, tmp_path, 11)


def test_control_and_source_age_are_not_hidden_by_normalization():
    value = {
        "vx": 0.6,
        "decision_age_s": 18,
        "source_observation_seq": 1140,
        "nested": {"target_commitment_source_id": "random-id", "deadline_ns": 79},
        "_debug_source": {"line": 1},
    }
    assert payload_clean(value) == {
        "vx": 0.6,
        "decision_age_s": 18,
        "source_observation_seq": 1140,
        "nested": {"deadline_ns": 79},
    }
