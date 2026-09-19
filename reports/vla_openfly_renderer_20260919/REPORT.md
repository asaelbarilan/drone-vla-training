# D151: native OpenFly renderer gate remains blocked locally

The user's Hugging Face access grant works. The official env_airsim_18 archive
is downloaded, SHA256/ZIP-CRC verified and extracted. This resolves the access
blocker. Local rendering has not passed: zero new camera images, zero new model
predictions, zero training updates, zero cloud resources. D150 source/action
reconstruction remains valid; it is not a rendered flight result.

## What was tested

Host: Windows RTX 4060 Laptop, 8 GB VRAM, Ubuntu 22.04.5 under WSL2. CUDA sees the
NVIDIA GPU. Vulkan reports software llvmpipe; WSLg OpenGL reports the Intel D3D12
adapter. GPU compute availability therefore did not establish usable native
Unreal rendering. The exact cause of the stall is still unresolved.

All attempts used the verified official Linux scene, an explicit 90-180 second
process timeout and isolated logs. The last five bound RPC to localhost:41489.
The first attempt ignored the CLI settings override and used the scene's
adjacent settings/default port; subsequent launches used its adjacent settings.
No user's Documents/AirSim configuration was edited.

| Attempt | Change / client | Measured result |
|---|---|---|
| 1 | Vulkan offscreen, CLI settings override | RPC started on default port; override not applied; stopped owned launcher |
| 2 | Adjacent settings, Vulkan offscreen/NoDisplay | RPC responds; stale spawn pose; image and camera-info requests timed out |
| 3 | Virtual display, Vulkan windowed, direct RPC | 15-second pose polling never reaches target; gate rejects it |
| 4 | Same rendering, official AirSim 1.8.1 SDK | Arming and source-style zero-velocity initialization succeed; image request times out |
| 5 | Requested OpenGL4 on virtual display | Same stale pose; gate rejects it. Vulkan libraries/llvmpipe threads remain loaded, so a distinct OpenGL backend was NOT verified |
| 6 | Vulkan virtual display, explicit ScalableClock, official SDK | Same stale pose and image timeout; clock change does not resolve it |

For attempts 3/5/6, requested NED position was
`[1901.6478438329495, 97.4708642670652, -4.008504278406168]`.
Reported position remained approximately `[0, 0, -0.1465]`: **1904.148 m error**.
Attempt 6 also records a **55-degree orientation error**. The SDK image request
timed out after about 16 seconds with a 15-second configured RPC timeout.
A successful RPC acknowledgement did not mean the scene applied the pose.

The official SDK follows the public source initialization: enable API, arm,
zero body-velocity asynchronous command, set pose, request front_custom RGB.
No model is involved in this failure. The SDK control rules out a simple custom
message-format or omitted-arming explanation; it does not identify the stall's
root cause. The first attempt to serialize attempt 6's SDK objects failed;
serialization was fixed and the same bounded run was probed again successfully
as a recorded failure. No successful image was lost or omitted.

Camera settings stayed at the official 1920x1080, 90-degree FOV and +1 m NED Z
camera offset. Unused lidar sensors/debug drawing were disabled in the scoped
runtime copies. The alternative clock is diagnostic only. Original scene settings
were restored byte-for-byte after all six renderers exited; localhost:41489 is
closed. No broad process kill, driver replacement or distro upgrade was performed.
The scene and logs remain on D:. The partial initial download is retained as an
unverified .part file, separate from the checksum-verified ZIP.

Added Ubuntu graphics/audio dependencies and then xvfb/xauth through signed apt
packages. A pre-existing ROS repository signing-key warning was not bypassed.
An independent unattended-upgrades process briefly held apt's lock; it was not
terminated. AirSim 1.8.1 was installed without dependency changes into a separate
scene-owned SDK directory, not into the model environment's package directory.

## Reproducible evidence and limits

`attempts/` preserves available launch commands, settings, logs and machine-readable
probe results. Attempts 1/2 were initial manual checks; their ad hoc RPC exceptions
were not saved as structured probe JSON. `official_settings.json` is a whitespace-normalized review copy; the restored
original-byte SHA256 is in status.json. `status.json` records final access,
cleanup and no-model/no-cloud status. D150's hardware_inventory.json is an older
snapshot from before access/setup, not the current status.

New scripts: `launch_openfly_renderer_probe.py`,
`probe_native_openfly_renderer.py` (earlier direct-RPC position/pixel diagnostic),
and `probe_official_openfly_renderer.py` (official SDK, pose/orientation/camera
position checks). Launches are capped at 300 seconds and reject an occupied port.
They are local WSL helpers, not a claimed portable Linux runner. Passing their
basic gate would still require image/channel/camera alignment against the recorded
source and expert-route rendering before scoring any model.

All scripts pass Ruff and compile/help checks. Actual negative live probes were
run against the simulator. The D150 33 focused data/action tests remain the latest
passing regression result; no core action/split/model code changed in D151.
The viewer labels its pose check separately from live execution. Its banner distinguishes recorded reconstruction from the failed
native rendering gate. A targeted isolated browser check confirms the banner,
route preview and mobile layout.

## Concrete next experiment, pending approval

Run the SAME scene and source-control pose on native Linux with NVIDIA Vulkan.
A short control separates this local WSL/runtime problem from a scene/package
problem. No training is part of this test. If expert capture passes, render
several verified expert poses, compare visual alignment, then attempt one bounded
route per model sequentially only within the remaining approved window. Failure
at the renderer gate produces no model flight score.

Proposed machine: **one g6.2xlarge in us-east-1 (N. Virginia)**, one NVIDIA L4
with 24 GB VRAM, 8 vCPUs, 32 GiB RAM. Maximum **2 running hours**. AWS's live public
Linux On-Demand price retrieved 2026-09-19 is **$0.9776/hour**, or **$1.9552** for
2 hours. Raw official pricing record is in `aws_price_quote.json`.

Use a free-license Ubuntu x86_64 image with a validated NVIDIA graphics/Vulkan
stack; a CUDA-only image is insufficient evidence. Exact AMI, account quota,
connection and graphics-driver support must pass read-only preflight before
launch. AWS CLI is not currently on this shell's PATH; no authenticated AWS
connection was used in this decision.

Temporary root/work disk: **100 GiB gp3**, standard included performance, retained
at most one day. This is for the single-scene diagnostic, NOT the full dataset or
the broader training-storage requirement. Using the AWS pricing page's $0.08 per
GB-month example gives about $0.267/day; regional disk pricing must be reconfirmed
in the actual launch quote. Public IPv4 adds $0.01 for 2 hours. Limit returned
artifacts to 1 GB; avoid paid AMI software, NAT gateways and snapshots.

Expected total is approximately **$2-3 before tax**, with a proposed **$5 total
spending limit** including storage/transfer/tax allowance. This is an operational
limit requiring verified prices, timed shutdown, artifact copying and prompt
cleanup, not an AWS-enforced instantaneous billing cap. Do not launch if the
actual configuration cannot fit it. Record new resource IDs; stop at the deadline,
copy evidence and delete only this disposable instance/volume after copy checks.
Approval must cover this concrete machine/cost and cleanup. No credit balance is
assumed. The earlier request to approve a machine before launch remains in force.

Sources checked:
- [AWS G6 specifications](https://aws.amazon.com/ec2/instance-types/g6/)
- [AWS official live Linux pricing feed](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20East%20(N.%20Virginia)/Linux/index.json)
- [AWS EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [AWS public IPv4 pricing](https://aws.amazon.com/vpc/pricing/)
- [Official AirSim clock configuration](https://github.com/microsoft/AirSim/blob/v1.8.1/docs/simple_flight.md)
- [Official AirSim client](https://github.com/microsoft/AirSim/blob/v1.8.1/PythonClient/airsim/client.py)

The baseline architectures, model weights, frozen dataset indices and protected
seeds 1-40/1060-1064 are unchanged. No new training or trustworthy cross-model
flight ranking can be claimed from this decision.
