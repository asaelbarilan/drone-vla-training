# D-112: six saved-frame passage decisions, no improvement

The model can name the red tower in a saved clutter image while pointing at the
adjacent gray obstacle. Both prompts do this. This establishes a specific failure
of image-location grounding in this case, before any waypoint execution. It does
not establish general VLM incapacity or exclude other navigation defects.

| Frozen case | Current point-only | Passage check + hold |
|---|---|---|
| Red tower visible through gap | Says "red tower", target(499,499), points on gray block | Names gray and red structures, same target(499,499), same wrong pixel |
| Target hidden, openings ahead | Gray structure labeled target(850,500), on right wall | Corrects kind to exploration, but(900,500) still on right wall |
| Close wall | exploration(500,500), on wall | Same wall point; does not use hold |

Zero of the three cases demonstrates an improved spatial choice. All six selected
pixels land on visually inspected gray obstacle faces. Hold was available only in
the candidate schema and was used zero times. Do not add this candidate to flight
runtime or run another flight on its strength. No new flight was performed.

## What is and is not isolated

The same RGB, mission, model digest, temperature, sampling seed, context limit,
output budget and coordinate contract were used within each pair. Baseline is the
D-111 grounded_v1 prompt, excluding the unpromoted color-guard trial. Candidate
adds a passage-check instruction and an explicit hold option. This is a combined
prompt/action-contract change, not an isolated prompt-only ablation. Its hold
placeholder coordinates are not executable in the existing flight runtime.

The visible red body occupies image x77..84,y72..97, annotated offline only.
Both model points decode to(111.388,111.388), whose RGB is(137,137,142), on the gray
block. The words "red tower" therefore do not validate the selected coordinate.
No separate target_visible question was asked, so presence understanding is inferred
from returned evidence/kind, not scored as an independent perception benchmark.

Actual unchanged OnFly policy code lifts all six responses using reconstructed
source depth/intrinsics/pose. Reprojection matches each chosen pixel within
3.18e-14 pixels. Thus this specific image-to-waypoint conversion faithfully follows
the wrong selection; it does not introduce the visible offset to the gray block.
The target/exploration point may stop before a wall because of depth/bearing/standoff
limits. A safe short segment is not proof that the selected semantic target is right.

Offline box-distance checks bound straight-segment clearance (sample spacing<=5 cm,
Lipschitz half-spacing subtracted): visible pair>=2.167 m, hidden pair>=4.173/4.654 m,
close-wall pair>=0.953 m. The close-wall segment meets0.6 m but not SUPER's1.2 m
margin. This does not test SUPER's alternate-route capability, dynamics, or prove a
passage impossible. Geometry and diagnostic RGB annotations never enter model input.

## Evidence, limits and next step

FREEZE.json records exact source frames, hash, source pose, depth, expectations,
paired prompts/schema and model options before calls. Two saved prefixes reproduce
1,040 poses; all three RGB inputs match original captures exactly. Expectations
were recorded before new replies. Annotated images are browser overlays only.
RESULTS.json stores decoded points, actual policy waypoints and geometry;
VERIFICATION.json verifies pair identity, options and pixel round-trip. Six raw
response files preserve model replies, prompts and schemas. Browser checks verify
six image panels, annotation toggle, and expandable exact prompt/reply; screenshots
are retained. Source and marked target/point images visually inspected.

Exactly six completed local gemma4:e2b calls; zero retries, zero cloud, zero flights.
All responses parse and lift successfully. Four diagnostic scripts pass lint;
no flight/runtime/default changes. Three selected single-frame pairs cannot establish
reliability, and serial model calls may vary even with fixed sampling options.

Next investigate pointing representation on these exact frames: can the model
localize the red body with a box or choose a labeled image region when direct
normalized-point output fails? First validate that interface offline, retaining an
absent-target control. Do not tune SUPER or add another flight before spatial choice
improves. This next experiment is not started or scheduled by this report.

Dashboard: http://127.0.0.1:8766/passage_choice.html
Rebuild without inference: python scripts/run_passage_probe.py --evaluate-only;
python scripts/report_passage_probe.py; python scripts/check_passage_probe.py.
