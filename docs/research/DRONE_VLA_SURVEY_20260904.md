# Drone VLA survey — read from the papers, not the reviews

Every row below was taken from the paper's own action or training-data section.
Where a review and a paper disagreed, the paper won. Rows marked "not stated"
are gaps I did not fill rather than guesses. Supersedes the review-derived
grouping in D-57.

## 1. Velocity output — our action space

| System | Action | Training data | Sim / real | Base model |
| --- | --- | --- | --- | --- |
| RaceVLA (2503.02572) | 4-D `(Vx, Vy, Vz, w)` | racing-drone set | real | OpenVLA, LoRA r=32 |
| CognitiveDrone (2503.01378) | 4-D velocity setpoints, ArduPilot-compatible | 8,000+ trajectories | sim | OpenVLA-7B |
| AutoFly (2602.09657) | 3-D velocity, de-tokenised from LLaMA2's last 256 tokens | 13,000 eps / 2.5 M triplets, incl. **1,000 real** | AirSim + real | Prismatic-VLM 7B |
| Exp2VLA (2607.03146) | 3-D `(vx, vz, yaw_rate)`, **normalised to [-1,1]** | 3,000 eps / 370,500 steps | Isaac Lab | pi-0.5, 4B |
| VLFly (2506.10756) | continuous linear + angular velocity | **none — training-free** | real (Tello Edu) | LLaMA + CLIP + ViNT |
| GRaD-Nav++ (2506.14009) | low-level control | **none — DiffRL in 3DGS** | sim, deployed real | MoE action head |

RaceVLA is the decisive citation: it states plainly that it replaced OpenVLA's
7-D manipulator vector with a 4-D drone signal of three linear velocities and
yaw rate. CognitiveDrone independently ties the same four fields to ArduPilot.
So `[vx, vy, vz, yaw_rate]` is a deliberate, hardware-grounded convention, and
the wider vectors seen in stored datasets are that convention padded into an
arm-shaped slot.

Note that Exp2VLA's zeroed channels are **not** only padding — the paper defines
its action as genuinely 3-D, deliberately omitting lateral velocity. D-56 called
the dataset defective and D-58 called it padding; both were partly wrong, and
this row is the accurate version.

## 2. Relative displacement

| System | Action | Training data | Sim / real | Base model |
| --- | --- | --- | --- | --- |
| UAV-Track VLA (2604.02241) | `[dx, dy, dz, dpsi]`, 25-step chunk | UAV-Track, 892,756 frames | CARLA | pi-0.5 |
| WorldVLN (2605.15964) | `(dx, dy, dz, dpsi)` | UAV-Flow + IndoorUAV-VLA | sim, real deploy | InfinityStar-8B |
| AerialVLA (2603.14363) | `<dx, dz, dpsi>`, 99 bins | TravelUAV, 7,922 traj / 420 k frames | AirSim | OpenVLA-7B, LoRA r=64 |
| Think Like a Pilot (2606.06836) | 4-D relative displacement + attitude change | 6,689 + 4,098 trajectories | UnrealZoo | **Qwen2.5-VL-3B + DiT-B, LoRA** |
| See, Point, Fly (2509.22653) | 2-D image waypoint, unprojected to 3-D displacement | **none — training-free** | real | any VLM |

## 3. Waypoint or pose

| System | Action | Training data | Sim / real | Base model |
| --- | --- | --- | --- | --- |
| **UAV-Flow Colosseo (2505.15725)** | 6-DoF pose at 5 Hz | **30,692 real + 10,109 sim** | **real — DJI Mavic 3T RTK, cm accuracy** | benchmarks OpenVLA-UAV, Pi-0-UAV |
| SpatialFly (2603.21046) | waypoint increment over 6-DoF pose | OpenUAV, 12,149 traj | AirSim | **Qwen2.5-3B + VGGT, LoRA r=36** |
| LongFly (2512.22010) | 3-D waypoint + Stop | OpenUAV, 12,149 traj | AirSim | Qwen2.5-3B |
| ImagineUAV (2606.01205) | 6-DoF waypoint references | UAV-Flow benchmark | sim + real tests | latent video diffusion, 1.3B |
| CosFly-Track (2605.17776) | nav waypoints + pose | 526 traces released | CARLA | not stated |
| UAV-VLA (2501.05014) | mission plan waypoints | 30 satellite images | real imagery | VLM |

## 4. Discrete primitives — where the scale is

| System | Action | Training data | Sim / real | Base model |
| --- | --- | --- | --- | --- |
| OpenFly (2502.18041) | discrete flight actions | 100 k trajectories, 18 scenes | UE / GTA V / Google Earth / 3DGS | OpenFly-Agent |
| IndoorUAV (2512.19024) | 4-DoF discrete, dual scale (0.15 m / 3 deg, 0.9 m / 15 deg) | 50,965 traj | Habitat, MP3D / Gibson / HM3D | pi-0, pi-0-FAST, OpenVLA, NaVid |
| FSD-VLN (2607.08359) | 8 primitives: Forward 3/6/9 m, Turn +-30 deg, Ascend/Descend 3 m, Stop | AirVLN-S + OpenFly, 30 k traj | UE | GR00T N1; **320 GPU-h on 4x RTX 4090** |
| AerialVLN | 4-DoF discrete | 8,400 trajectories | UE | — |

## Conclusions

**There is no single field-wide convention.** The field splits four ways on what
an action even is, and the split is roughly even by paper count. What *is*
settled is narrower and still useful: among models that emit velocity, the
representation is `[vx, vy, vz, yaw_rate]`, because that is the MAVLink /
ArduPilot setpoint interface. Our action space is standard for its class.

**The scale sits in the representations we cannot use.** OpenFly (100 k) and
IndoorUAV (51 k) are the largest corpora and both are discrete primitives.
Converting a primitive into a velocity requires inventing the magnitude, so
their size is unavailable to us.

**UAV-Flow is the only large real-world corpus**, and it stores 6-DoF pose at a
uniform 5 Hz rather than actions — so velocity is a finite difference, which was
verified numerically on one trajectory (vx -0.51, vy 0.92, vz 0.00 m/s).

**Two systems reach real-world performance with no training at all.** VLFly and
See, Point, Fly are training-free: a pre-trained VLM grounds a waypoint in the
image and geometry does the rest. Given an 8.6 GB budget this is a serious
alternative, and it is close to what C5 OnFly already does.

**Hardware-matched precedents exist.** Think Like a Pilot (Qwen2.5-VL-3B + LoRA
+ DiT action head) and SpatialFly (Qwen2.5-3B + LoRA r=36) are both roughly 3 B
with LoRA and frozen encoders. FSD-VLN reports 320 GPU-hours on 4x RTX 4090,
which sets the expected order of magnitude for a run of this kind.
