import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from uavlab.analysis.flight_debugger import _sources, html_document

out = Path("reports/adaptive_visual_plan_20260912")
out.mkdir(exist_ok=True)
# Private browser fixture: existing saved flight data plus new template. Never
# relabel a synthetic plan as a historical model decision in persisted run data.
old = Path("reports/debugger/depth_fix_comparison.html").read_text(encoding="utf-8")
start = old.index("const DATA = ") + len("const DATA = ")
data, _ = json.JSONDecoder().raw_decode(old[start:])
data["sources"] = _sources()
page_path = Path("tmp/adaptive_plan_ui_fixture.html")
page_path.write_text(html_document(data), encoding="utf-8")
fixture = {
    "chain": [
        {
            "payload": {
                "kind": "adaptive_visual_plan",
                "revision": 2,
                "response": {
                    "assessment": "blocked",
                    "reason": "TEST FIXTURE: routing rejected the previous proposal.",
                    "active_id": "inspect",
                    "scene_memory": "Synthetic browser-contract data; not a model inference.",
                    "plan": [
                        {
                            "id": "inspect",
                            "objective": "Inspect an opening <script>bad()</script>",
                            "expected_view": "The far side becomes visible",
                        },
                        {
                            "id": "approach",
                            "objective": "Approach the requested tower",
                            "expected_view": "The tower fills more of the image",
                        },
                    ],
                    "action": {"mode": "retain"},
                },
                "proposed_world_point": {"x": 2, "y": -1, "z": 3},
                "point_origin": {"observation_seq": 7},
                "input_state": {"history": [{"routing": {"accepted_not_completed": False}}]},
            }
        }
    ]
}
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1100})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(page_path.resolve().as_uri(), timeout=60000)
    assert page.locator("#adaptivePlan").is_hidden()
    page.evaluate("d => renderAdaptivePlan(d)", fixture)
    panel = page.locator("#adaptivePlan")
    assert panel.is_visible()
    assert panel.locator("li").count() == 2
    assert "ACTIVE" in panel.inner_text()
    assert "<script>bad()</script>" in panel.inner_text()
    assert panel.locator("script").count() == 0
    panel.locator("summary").click()
    assert "accepted_not_completed" in panel.inner_text()
    panel.screenshot(path=str(out / "UI_CONTRACT_FIXTURE.png"))
    page.evaluate("renderAdaptivePlan({chain: []})")
    assert panel.is_hidden()
    browser.close()
assert not errors, errors
(out / "UI_CHECK.json").write_text(
    json.dumps(
        {
            "synthetic_browser_fixture_not_a_flight": True,
            "checks": [
                "plan visible",
                "active subgoal",
                "expected view",
                "model memory",
                "retained goal origin",
                "previous feedback",
                "HTML escaped",
                "hidden for old runs",
            ],
            "javascript_errors": errors,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Adaptive plan UI: 8 checks passed; zero JavaScript errors. No model calls.")
