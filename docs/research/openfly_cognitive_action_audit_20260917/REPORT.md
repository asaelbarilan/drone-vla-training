# OpenFly action representation and CognitiveDrone data

Targeted two-paper review requested by the user, 2026-09-17. Scope deliberately excludes a broad model survey. Questions: why discrete OpenFly actions, evidence of superiority, CognitiveDrone release/terms and compatibility. Search: paper titles, official project links, Hugging Face metadata and official code tree; stop after primary methods and linked releases are inspected. No training or bulk media download performed.

## Findings

OpenFly v6 section4.1 explicitly follows mainstream VLN work in using discrete actions. Forward3m dominates labels; adding6m/9m granularities mitigates imbalance. Section3.2/AppendixE uses action-space A* trajectory generation; AppendixC unifies engines under metre-based FLU. The paper also supports continuous-waypoint generation. Section5 describes six action types; the released eight-component vector is an implementation encoding, not eight physical degrees of freedom. No inspected ablation establishes superiority of that eight-entry encoding over velocity targets. Existing experiments compare models/history mechanisms, not that representation choice.
Source: https://arxiv.org/html/2502.18041v6

CognitiveDrone paper reports8062 simulated trajectories, human recognition, symbol understanding and reasoning. It describes4D velocity/yaw control and10Hz control, Gazebo/ArduPilot, with camera spline data collection. This is potentially complementary to OpenFly scene/route diversity and closer to our task-category comparison; physical real-world flight data is not established by this description.
Source: https://arxiv.org/html/2503.01378v1

The official project links ArtemLykov/CognitiveDrone_dataset. It is public and ungated; README explicitly instructs training from data/rlds/train and evaluating using benchmark/validation. Current listing contains30 TFRecord shards named of-00128, not all128. Do not assume the published8062 episodes are all released here. No dataset license file or YAML license metadata found; official linked collector tree also has no license file. Public availability and explicit intended training use are verified; a specific permissive license is not.
Sources: https://cognitivedrone.github.io/ ; https://huggingface.co/datasets/ArtemLykov/CognitiveDrone_dataset ; https://github.com/SerValera/docker_CognitiveDrone_DataCollector

Community LeRobot conversion kingJulio/cognitive_drone_lerobot has1766 episodes/104483frames,10Hz, two256x256camera features,5Dstate and7Dactions; action dimension names are not documented in its info.json. No card/license metadata. It is not the official full release. Do not assume seven independent controls or a ready4D mapping.
Source: https://huggingface.co/datasets/kingJulio/cognitive_drone_lerobot

## Admission plan

Add CognitiveDrone as a candidate for symbol/reasoning/recognition tasks alongside OpenFly navigation. Before optimizing: inspect one official TRAIN shard; map all action fields, coordinates, units and timing from source/data; establish available category counts; preserve benchmark validation and freeze task/trajectory-disjoint development splits. Clarify dataset reuse terms before treating it as permissively licensed or redistributing a combined corpus. No author contact sent. Do not silently convert OpenFly primitives to arbitrary-duration velocities. No AWS spending or protected local seeds used.
