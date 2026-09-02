# OnFly evidence review

Primary defining source: *OnFly: Onboard Zero-Shot Aerial Vision-Language
Navigation toward Safety and Efficiency*, arXiv:2603.10682v1 (2026). Official
resource: `Robotics-STAR-Lab/OnFly` (inspected 2026-08-25).

## Decision-relevant findings

- The architecture is a shared-perception dual agent, not a waypoint policy
  with an ad-hoc stop heuristic: high-rate image-goal prediction and low-rate
  progress classification use separate contexts and rates.
- Decision output is an integer image point. The previous 3D goal is
  reprojected into the current frame as a lightweight history cue.
- Monitoring is forced choice: `CONTINUE`, `STOP`, or `LOST`. Hybrid memory is
  `[initial, four keyframes, latest]` and is designed for global context and
  prefix-stable cache reuse.
- Verification combines semantic-local refinement and depth feasibility. A
  Gaussian bearing gate prevents an edge pixel from becoming an aggressive
  long forward command.
- A receding-horizon ESDF planner is load-bearing. The paper reports that
  removing it raises collision rate from 2.7% to 37.5% and reduces success from
  67.8% to 35.8%.
- Paper settings include 720p, 90x60 degree FOV, `D_max=7 m`, maximum speed and
  acceleration 0.6 m/s, maximum yaw rate 0.4 rad/s, monitoring every 2 s,
  keyframe budget 4, feature threshold 0.5, and obstacle dilation 0.2 m.
- The paper evaluates Qwen3-VL-4B-AWQ and reports 0.81 s decision latency and
  1.15 s hybrid-monitor latency on Jetson Orin NX. Its success radius is 5 m;
  the testbed retains its stricter canonical success condition.

## Resource audit

- Paper: full method and result tables available.
- Official repository: public, seven commits visible, but README says `Code
  coming soon`; no implementation, license, checkpoint, or deployment package
  is released.
- Consequently, exact prompt text, feature tensors, cache protocol, keyframe
  thresholds, semantic ROI code, and Fast-Planner modifications cannot be
  source-validated. Those gaps are locked in `ONFLY_IMPLEMENTATION_LOCK.md` and
  are not silently guessed as paper facts.

The shared evidence ledger remains the 31-work UAV autonomy review in
`spf_evidence.json`; OnFly is one of its direct implementation targets.
