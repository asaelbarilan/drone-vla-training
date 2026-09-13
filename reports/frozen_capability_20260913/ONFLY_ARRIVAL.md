# Source-aligned OnFly arrival observation

Run frozen_c5_visible_target_20260913_s1061 repeats the visible-goal failure:
closest 0.3349479 m at 13.05 s, no stop, final approximately 29.68 m.
1200 poses replay exactly. Camera/map directly inspected at 9.95, 11.95,
13.05 and 14 s; frame captures are under browser/c5_arrival/.

call-000017 monitor samples obs 200 at 9.95 s, starts at 10 s, returns at
11.2 s. It identifies the red target at (499,500); selected measured range is
2.092187 m, above the 2 m arrival bound. Monitor therefore emits CONTINUE.
The next monitor image is obs 240 at 11.95 s, available 13.2 s: camera has
no red target (also directly seen in debugger). It returns visible=false,
causing LOST/recovery. Drone was already 0.380269 m from the scored goal at
that sample and reaches 0.334948 m at 13.05 s. No stop is executed.

Observed boundary: current-image identification/range/confirmation and control
movement do not produce an accepted stop during this arrival. This is not an
inability to reach the target. A single trace does NOT establish which intervention
would repair it: target persistence, approach control, sampling, geometry/near-plane
rendering and completion semantics must be isolated before a causal claim.
Current monitor also interprets arbitrary mission instructions as one visual
destination, so coordinate, ordered and dynamic tasks require contract scrutiny.
No runtime change, relaxed threshold, added memory or extra inference in this audit.
