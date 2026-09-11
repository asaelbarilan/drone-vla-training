# Passage probe from the user's selected 41.60 s state

D-95, September 12, 2026. Privileged manual physical diagnostic. Zero model calls.

Source: `c5_guarded_monitor_20260911_s1061`, t=41.60 s, observation 833.
Replayed all preceding controls to preserve full simulator state. Every checked
logged position matches exactly. Both branches begin with identical state:
position (18.0505054233, 11.2603843951, 2.4879334073) m;
velocity (-0.3390547438, -0.2232031216, -0.0147360802) m/s;
yaw 82.0517686876 degrees. No teleport or velocity reset.

| Manual command | Result | Elapsed | Minimum center-to-wall distance |
|---|---|---:|---:|
| 0.6 m/s along original 82.05 degree heading | First collision with left obstacle; terminated | 9.85 s | 0.3741 m at detection |
| 0.6 m/s toward visually selected gap column u=128/224, bearing 74.01 degrees | Cleared both obstacles without collision | 19.50 s | 0.6130 m |

The drone body radius is 0.4 m, so the successful route leaves a minimum
body-to-wall gap of 0.213 m. The 8.04-degree aiming change is the controlled
command difference. Both preserve the same acceleration lag; the second camera
yaw turns toward its command within the existing 0.4 rad/s yaw-rate bound.
Altitude receives zero vertical velocity command; the initial vertical drift
therefore settles identically in both trials, at z=2.473934 m.

The visible bounding boxes are longitudinally staggered: right box y=11.2208
through 14.3104 m; left box y=16.7112 through 21.3413 m. A visual slit or the
0.6864 m difference between their x faces is not a constant-width overlapping
corridor. The observed diagonal crossing is a direct physical counterexample
to declaring the whole opening impassable to a 0.8 m diameter body.

The configured local planner clearance is 0.6 + 1.2 = 1.8 m. The successful
manual route's 0.613 m center-to-surface clearance does not meet that nominal
parameter. The actual planner uses a sparse range-based occupancy map, including
body-aware ray hits, so parameter comparison alone does not prove precisely
which planner check caused the original stall. No clearance parameter was
changed and the planner was not run in these manual probes.

## Artifacts

- `index.html`: portable two-video comparison; local preview copied to
  `reports/debugger/passage_4160.html`.
- `heading.mp4`, `opening.mp4`: synchronized close-up map and actual simulated
  drone camera. H.264, 1160 x 710, 10 fps. Initial/final holds add about 3 s.
- `heading.json`, `opening.json`: per-tick dynamics, commands, collision state,
  surface clearances and obstacle geometry.
- `source_4160.png`: exact starting replay frame.
- `comparison.png`: both endpoints.

Reproduce with `PYTHONPATH=src` and `python scripts/probe_passage_4160.py`.
No inference backend is constructed. Simulator collision detection only sets a
flag; the probe explicitly terminates at its first occurrence to avoid falsely
claiming a pass after tunneling through a wall. Control step is 0.05 s.

## Interpretation

The user was right to demand a physical visual test of the bottleneck. The
results distinguish aiming from physical fit and configured clearance. They
do not establish that the VLM was right or wrong throughout the saved flight,
nor that more time would complete the original mission. Next inspect the
planner's inferred geometry and route commitment at the same state; do not
change safety margins on the basis of a single manual pass.
