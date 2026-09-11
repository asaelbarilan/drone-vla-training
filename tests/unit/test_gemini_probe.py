from urllib.error import HTTPError

import pytest

from uavlab.plugins.inference import gemini_client as probe


def test_path_configuration_reads_existing_key_file(tmp_path):
    key = tmp_path / "key.txt"
    key.write_text("GEMINI_API_KEY=test-key\n")
    env = tmp_path / ".env"
    env.write_text(f"GEMINI_API_KEY_FILE={key.as_posix()}\n")
    assert probe.key_from_file(probe.configuration(env)) == "test-key"


def test_unconfirmed_billing_never_calls_network(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "urlopen", lambda *a, **k: pytest.fail("network called"))
    with pytest.raises(ValueError, match="billing"):
        probe.invoke({}, "test", tmp_path / "frame.png", tmp_path / "stop")


def test_quota_stops_once_and_prevents_subsequent_calls(monkeypatch, tmp_path):
    key = tmp_path / "key.txt"
    key.write_text("test-secret")
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"test image")
    calls = []

    def limited(request, **kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, 429, "limit", None, None)

    monkeypatch.setattr(probe, "urlopen", limited)
    settings = {"GEMINI_API_KEY_FILE": str(key), "GEMINI_FREE_TIER_CONFIRMED": "true"}
    stop = tmp_path / "stop"
    with pytest.raises(RuntimeError, match="429"):
        probe.invoke(settings, "test", frame, stop)
    assert stop.exists()
    with pytest.raises(ValueError, match="Quota stop"):
        probe.invoke(settings, "test", frame, stop)
    assert len(calls) == 1
    assert "test-secret" not in calls[0].full_url
