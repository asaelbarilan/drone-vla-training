# D-113: grid and box localization have different failures

Six local Gemma calls on the same three saved scenes are complete. Neither format
is ready to drive navigation. No runtime change or new flight was made.

| Saved scene | 4x4 labeled grid | Tight box on original RGB |
|---|---|---|
| Red tower visible through gap | B2, correct coarse cell | Visible=true; box[364,333,633,384], incorrect localization |
| Red absent, openings ahead | C3, false positive | Visible=false, correct absence |
| Red absent, close wall | B1, false positive | Visible=false, correct absence |

The visible box decodes to x81.253..141.300,y74.333..85.718 in224x224 pixels.
It is a horizontal strip covering mostly the gray neighbor. The true visible red
bounds are[77,72,85,98] in half-open pixel coordinates. IoU=0.05024, below frozen
0.5 threshold; its center is outside the target. A verbal description of the red
structure still does not ensure that generated coordinates localize it.

Grid coarse-case correctness is1/3; box-task correctness is2/3 because it rejects
the two absent scenes. These are different criteria, not a model ranking. There
is only one positive frame and two negatives. Correct B2 selection cannot be called
reliable localization or evidence that the exact red body is grounded precisely.
Combining the two formats post hoc would be an untested new mechanism, not a success
already established by these results.

## Controls and limits

FREEZE.json was committed before inference. Expected grid cell B2/absences, visible
red bounds, box center and IoU criteria were fixed first. Three original RGBs are
byte-identical to D-112 sources. Grid input retains224x224 RGB with neutral labels
and lines; visible red pixels are unchanged, but other image regions are intentionally
annotated. Bounding-box input is the unmodified original. Green/yellow reference
and prediction overlays appear only in the report, not in the model inputs.

Both tasks are localization-only, unlike D-112's navigation prompt. Grid and box
conditions change both representation and image annotation. Therefore they do not
isolate numeric format alone, and improvement in one positive example cannot be
attributed solely to the grid. Same pinned gemma4:e2b/options across six calls,
including seed0,temperature0,num_ctx8192,num_predict192. No retries/cloud/extra model.

Six raw responses, exact prompts/schemas/options, original/annotated input hashes,
RESULTS.json and VERIFICATION.json are retained. All six responses are valid under
the declared format. Three diagnostic scripts pass lint. Browser QA verifies six
image panels, diagnostic-overlay toggle, exact prompt/reply expansion; screenshots
saved and positive pair visually inspected. No need for flight regressions because
runtime,model configuration and flight profiles were not changed.

## Implication

The numeric-point interface is not the only demonstrated issue. Coarse grid selection
can find this visible target but invents targets when none are present; boxes can
express absence but mislocalize the visible object. Keep presence and localization
as separate measurable failures. A next validation should add independent positive
and absent frames before selecting or combining formats. No further call/flight is
scheduled here, and neither interface is promoted.

Dashboard: http://127.0.0.1:8766/localization_formats.html
Rebuild without inference: python scripts/localization_formats_probe.py evaluate;
python scripts/report_localization_formats.py; python scripts/check_localization_formats.py.
