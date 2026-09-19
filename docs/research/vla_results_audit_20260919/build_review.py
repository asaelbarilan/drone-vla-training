"""Build the drone-only literature ledger and readable artifacts from audited facts."""
from pathlib import Path
import json, html
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
CACHE=ROOT/'.local/drone_vla_papers_20260919'
manifest=json.loads((CACHE/'manifest.json').read_text(encoding='utf-8'))
byid={x['id']:x for x in manifest}
works=[]
def add(key,title,mechanism,action,result,protocol,locator,data,compute,limits,code='Not verified in inspected paper/resources.',weights='Not verified in inspected paper/resources.',licenses='No applicable resource license verified.',category='direct_solution'):
 m=byid[key];v=m.get('version');url='https://arxiv.org/abs/'+v if v else m['url']
 row=dict(id=key,title=title,year=int('20'+v[:2]) if v else 2026,url=url,source_type='preprint' if v else 'conference_paper',category=category,decision_relevance=mechanism,supported_claims=[result],datasets=data,metrics=protocol,code=code,data=data,weights=weights,licenses=licenses,compute=compute,limitations=limits,inspection_level='methods_results',action_interface=action,result=result,source_locator=locator,version=v or 'AAAI 2026 publisher PDF',pdf_sha256=m.get('sha256'),main_architecture=category=='direct_solution')
 works.append(row)
add('openfly','OpenFly-Agent','History-aware token policy; central reproduction target.',
 'Native discrete flight primitives with subset-specific normalization; not our FRD velocity JSON.',
 'SR 34.3% seen / 22.6% unseen; real-flight SR 26.09% on 23 trials.',
 'Stop within 20 m; collision fails. OSR counts reaching that radius at any point: 64.3% / 56.2%. Seen 1,800 and unseen 1,200 routes.',
 'v7 sections 6.1-6.5, Tables 2-3; real-flight appendix I.',
 'OpenFly: about 100k training trajectories, rendered scenes including real-world reconstructions. Official raw and RLDS repositories exist.',
 '7B; batch 64; real model runs on external PC, with onboard Super trajectory planner and MPC.',
 'v7 paper results are not established for our downloaded checkpoint. Offline action agreement is not flight SR. Do not equate rendered real-scene imagery with real-flight demonstrations.',
 'https://github.com/SHAILAB-IPEC/OpenFly-Platform',
 'https://huggingface.co/IPEC-COMMUNITY/openfly-agent-7b (files verified)',
 'Code/model MIT; dataset repositories declare Apache-2.0. Underlying scene assets may have separate terms.')
add('cognitive','CognitiveDrone','OpenVLA velocity policy, optionally assisted by a reasoning VLM.',
 'vx, vy, vz, yaw rate; optional high-level reasoning stream.',
 'Normalized benchmark score 59.6% base / 77.2% R1 reasoning variant.',
 'Correct cognitive gate decisions across task categories; this aggregate is not unrestricted outdoor mission success.',
 'Sections III-V and benchmark results figure.',
 '8,062 simulated trajectories in Gazebo/ArduPilot; official cognitiveDrone_dataset HF repository verified.',
 'OpenVLA 7B; LoRA rank 32; 4,000 updates, batch 64, four A100 GPUs; policy 10 Hz, reasoning 2 Hz.',
 'Simulator cognitive tasks; physical-flight performance is not established by these scores. Final model release not verified.',
 'https://github.com/SerValera/docker_CognitiveDrone_DataCollector (collector)',
 licenses='No code/data license metadata verified; public accessibility alone is not reuse permission.')
add('racevla','RaceVLA','Direct learned velocity policy with real-drone demonstrations.',
 'vx, vy, vz, yaw rate to ArduPilot.',
 'Real task-category results: visual 79.6%, motion 75.0%, physical 50.0%, semantic 45.5%.',
 '200 real generalization experiments distributed across categories; not the OpenFly route benchmark.',
 'Sections III-V, Figure 6.',
 '200 real demonstration episodes, approximately 20k images; official RaceVLA_dataset verified.',
 'OpenVLA 7B; LoRA rank 32, 7k steps, single A100. INT8 inference on offboard RTX4090 at 4 Hz.',
 'Its comparison with manipulation OpenVLA category scores is not a matched physical-task comparison. Limited route/task diversity.',
 'https://github.com/SerValera/RaceVLA',
 'https://huggingface.co/SerValera2/RaceVLA_models (64 files verified)',
 'No explicit code/model/data license metadata verified; project links correct stale README HF owner.')
add('autofly','AutoFly','RGB plus learned pseudo-depth action policy.',
 'Tokenized 3D velocity vector; navigation policy plus flight control stack.',
 'Simulation overall SR 47.9%, CR 21.9%; real indoor/outdoor SR 60% / 55%.',
 'Goal distance <=5 m and alignment <=15 degrees; real result uses 10k simulated +1k real training trajectories.',
 'Tables 2-3; Appendix A.2.1 thresholds and A.3/A.5 deployment.',
 'Custom AirSim and real-flight navigation corpus, around 13k trajectories; complete public data release not verified.',
 'Prismatic 7B; 80k training steps; distributed offboard model/onboard control deployment.',
 'Not pure zero-shot sim-to-real. Official linked xlsun/AutoFly model API returned 401; usable public weights not verified.',
 'https://github.com/xiaolousun/AutoFly-VLA',
 'https://huggingface.co/xlsun/AutoFly (401 during unauthenticated check)',
 'Code license metadata absent; weight/data licensing unresolved.')
add('aerialvla','AerialVLA / AeroVLA (Xu et al.)','Dual-camera minimal aerial action policy; distinct from the AAAI dialogue paper.',
 'Forward/vertical/yaw displacement bins and intrinsic landing signal; not metric velocity bins.',
 'SR 47.96% seen / 56.60% unseen objects / 37.58% unseen maps.',
 'TravelUAV/OpenUAV splits; 20 m navigation success. Input includes front/down cameras and a directional prompt.',
 'Methods section 3; Tables 2-4.',
 'TravelUAV; training annotations in official repository.',
 'OpenVLA 7B aerial LoRA; native two-camera and prompt interfaces required.',
 'Unseen objects and unseen maps are different splits. Simulation score does not establish physical landing accuracy; audit directional-hint availability before transfer.',
 'https://github.com/XuPeng23/AeroVLA',
 'https://huggingface.co/XuPeng23/AerialVLA (adapter files verified)',
 'Code and adapter declare Apache-2.0; inspect underlying dataset/asset terms separately.')
add('spatialfly','SpatialFly','Implicit 3D geometry features condition waypoint prediction.',
 '3D waypoint increments; visual, geometric and state inputs.',
 'Full-training SR 38.54% seen / 25.46% combined unseen / 13.57% unseen maps.',
 'OpenUAV continuous navigation; keep full-data and 25%-data settings separate.',
 'Methods and experimental setup; Tables I-III.',
 'OpenUAV/TravelUAV benchmark splits.',
 'Qwen2.5 3B, CLIP and VGGT encoders; LoRA, eight RTX4090 GPUs.',
 'Different sensor/prompt assumptions from OpenFly; no exact official code/weights verified in paper or targeted search. Real-flight result not established.')
add('longfly','LongFly','Compressed visual history and trajectory history support long routes.',
 'Continuous 3D waypoints and stop.',
 'SR 36.39% seen / 43.87% unseen objects / 11.27% unseen maps.',
 'OpenUAV; stop within 20 m. Seen OSR 65.87% is much higher than seen SR.',
 'Methods section III; Tables II-IV.',
 'OpenUAV, 12,149 trajectories across benchmark partitions.',
 'Qwen2.5 3B; LoRA with frozen visual encoder; exact training cost not independently measured.',
 'History and stopping matter; goal-hint access requires audit. No official code/checkpoint verified in targeted search; real-flight validation not established.')
add('flight','FLIGHTVLA / Think Like a Pilot','Asynchronous reasoning VLM and diffusion action head.',
 'Dense flight trajectory/action chunks conditioned on delayed semantic features.',
 'Long-horizon Flow SR 59.0%; Fine-grained VLN SR 13.5% and instruction-adherence SR 11.0%.',
 'Flow requires all subtasks; VLN SR uses stop within 15 m; adherence additionally requires the instructed sequence.',
 'Sections 4-5, Table 2(a,b).',
 'FLIGHT: 6,689 fine-grained VLN and 4,098 long-horizon Flow trajectories.',
 'Qwen2.5-VL 3B plus DiT-B; separate low-frequency semantics and high-frequency action generation.',
 'The two scores are different tasks, not contradictory model performance. Simulation results; final model file availability not established by a dataset link.',
 'https://github.com/buaa-colalab/FLIGHT',
 'Project links Dataset & Models to https://huggingface.co/datasets/jujujulien/FLIGHT; checkpoint verified status unresolved.',
 'No code/data/weight license metadata verified.')
add('worldvln','WorldVLN','Autoregressive world model with learned action decoding.',
 'Predicted future visual latents decoded into aerial motion/pose actions.',
 'UAV-Flow-Sim SR 79.12% fixed-language / 78.02% open-language; IndoorUAV-VLA SR 41.76%.',
 'Flow semantic completion and IndoorUAV endpoint/heading precision are distinct protocols.',
 'Sections 3-4, Tables 1-2 and Appendices A.4-A.7.',
 'Trained/adapted on UAV-Flow and IndoorUAV-VLA; not a zero-shot off-the-shelf comparison.',
 'InfinityStar backbone; training eight A800 80GB GPUs, simulator RTX4090.',
 'Model size and latency differ from our small adapters. Scores do not imply real-flight reliability.',
 'https://github.com/EmbodiedCity/WorldVLN.code',
 'https://huggingface.co/EmbodiedCity/WorldVLN (backbone and action-decoder files verified)',
 'Repository CC-BY-4.0; model card license metadata absent; dataset terms separate.')
add('imagineuav','ImagineUAV','Video world-action model followed by kinodynamic planning.',
 'Future video to estimated 6-DoF motion to planner-refined trajectory.',
 'Flow-Sim SR 70.9% full / 68.9% distilled; real flights 13/20 with planner versus 9/20 without.',
 'Ten real tasks repeated twice; native UAV-Flow-Sim task completion.',
 'Tables I-III and experiments/deployment sections.',
 'UAV-Flow; real flight evaluation uses an additional planning stack.',
 '1.3B world-action model; distilled pipeline 6.2 seconds on RTX PRO6000; fast trajectory tracking is separate.',
 'A slow inference stage can coexist with faster control. Small real denominator; no official model/code release verified from paper or targeted search.')
add('exp2vla','Exp2VLA','Aerial expert demonstrations adapt pi0.5 and SmolVLA action experts.',
 'Normalized vx, vz and yaw-rate action chunks; no independent lateral command.',
 'pi0.5: 84.10% single-object, 65.0% multicolor, 51.7% color-permuted; SmolVLA: 46.60% single-object and 15.0% multicolor.',
 'Isaac Lab, stated 500 episodes/task, 0.60 m goal radius. Equation/algorithm accept any-time radius entry, although prose mentions stabilizing.',
 'Tables I-V; Algorithm 1 and section IV.',
 'MultiObject training table: 1,500 episodes / 370,500 timesteps /0.98GB; separate SingleCube dataset.',
 'Reported pi0.5 run: 60k steps, batch16, BF16, frozen SigLIP; action expert trained.',
 'SmolVLA is not our SmolVLM JSON adapter. Several bibliography IDs do not match their titles; denominator/rounding and stabilization criterion need reproduction. No physical-flight SR demonstrated.',
 'Training pipeline described; a complete official training-code repository not verified.',
 'Final adapted checkpoints not verified; official HF dataset exists.',
 'HF dataset license metadata absent; underlying backbone terms do not grant dataset permissions.')
add('fsdvln','FSD-VLN','Fast diffusion actions and slow semantic memory.',
 'Temporal action generation mapped to aerial primitives, including merged forward actions.',
 'SR 26.7% seen /13.6% unseen; authors reproduce OpenFly at 18.5% /5.1% on their own test set.',
 'Stop within 20 m; different evaluation scenes/split from OpenFly paper.',
 'Section 4.1-4.3, Table 1 and its self-reproduction footnote.',
 'Over 30k AirVLN-S/OpenFly trajectories from selected urban scenes.',
 'GR00T N1 initialization; frozen visual-language encoder, trained decision/state/action modules.',
 'Its OpenFly numbers are not an independent reproduction of the original benchmark. No official resources verified in paper or targeted search; simulation evidence only.')
add('uavtrack','UAV-Track VLA','Flow action model with auxiliary spatial grounding for moving targets.',
 '25-step chunks of delta position and yaw.',
 'Far pedestrian tracking SR 61.76% seen /55.00% unseen; vehicles 37.88% /27.91%.',
 'CARLA tracking survival, distance/angle loss limits, maximum 500-step episodes; not fixed-goal navigation.',
 'Sections 3.4 and 5.1, Tables 2-3.',
 'CARLA embodied tracking dataset with over 890k frames.',
 'pi0.5-based spatial auxiliary head and flow matching action expert; flight hardware not evaluated.',
 'All reported experiments are in CARLA. Project page reachable; exact released trained weights/data not verified.',
 'https://flying-intelligence.github.io/ (project; paper mentions Hub-Tian/UAV-Track-VLA, not yet release-verified)')
add('vlaan','VLA-AN','Learned semantic waypoints with geometric safety correction and replanning.',
 '3D waypoints, yaw, replan signal; depth-based action module adjusts unsafe trajectories.',
 'Table 3 reports 98.1% object-navigation and 85.7% long-horizon SR.',
 'Authors own eight task categories; precise acceptance tolerances and trial denominators not located.',
 'Sections 3-4, Table 3; Table 2 is a separate dataset-composition ablation.',
 'Custom real, mesh and 3D Gaussian Splatting mixture; quantity/release not verified.',
 '2B/3B/7B deployment variants; Orin NX16GB; optimized example 494ms inference.',
 'High result is a whole system on different tasks, not evidence of 98% OpenFly success. Missing evaluation detail and no official release found limit reproducibility.')
add('gradnav','GRaD-Nav++','Compact CLIP-conditioned policy trained with differentiable reinforcement learning.',
 'Three body angular rates plus normalized thrust; genuinely lower-level than waypoint/velocity VLAs.',
 'Real two-stage tasks:16/24 trained and6/12 unseen combinations; simulation table20/24 and9/12.',
 'Correct gate traversal then finish closer to target than distractors; unseen means new combinations of known subtasks.',
 'Sections III-IV, Tables II-III and limitations.',
 '3DGS environments, eight training tasks and four recombined held-out tasks.',
 'CLIP150M plus small MoE; single RTX4090 training; Orin Nano onboard around25Hz overall.',
 'Real sample small; fails instructions with entirely unseen subtasks. Simulation table caption says six trials/task but printed denominators do not match; retain printed counts.',
 'https://github.com/Qianzhong-Chen/grad_nav',
 'README provides local checkpoint paths and linked map assets; a complete released matching checkpoint not verified.',
 'GitHub reports NOASSERTION for repository license; reuse terms need inspection.')
add('uavflow','UAV-Flow Colosseo','Supporting aerial benchmark for pose/action models, not an extra architecture in the main count.',
 'Pose trajectories / action chunks with ground-drone execution look-ahead.',
 'Source defines simulation SR through inspection of whether the executed trajectory fulfills the instruction; real deployment examples are qualitative.',
 'Ten Flow behavior types, fixed/open language, SR plus pose-aware NDTW; not exact next-action classification.',
 'Sections3.2 and4.2-4.3; Appendices C-E.',
 'UAV-Flow real trajectories and UAV-Flow-Sim synthetic trajectories; public HF data verified.',
 'OpenVLA-UAV training8A100, pi0-UAV8RTX4090; ground-station deployment.',
 'Recorded poses are achieved motion, not automatically commanded velocities. Manual semantic scoring differs from automatic endpoint thresholds.',
 'https://github.com/buaa-colalab/UAV-Flow',
 'https://huggingface.co/wangxiangyu0814/OpenVLA-UAV (files verified)',
 'Code Apache-2.0; HF data/model license metadata absent.',category='dataset_benchmark')
add('indooruav','IndoorUAV','Supporting benchmark reveals sensitivity to task horizon and precision.',
 'Short pose-control sequences and long-horizon navigation.',
 'Fine-tuned pi0 gets27.16% short-horizon VLA SR; OpenFly-Agent gets4.12% seen /2.58% unseen long-horizon VLN SR.',
 'VLA: final distance<0.5m AND yaw error<pi/4 (45 degrees); VLN: distance<2m. These are different tasks.',
 'Tables2-3; evaluation metrics and appendix equations3-4.',
 'Habitat-derived indoor environments; short VLA and long VLN subsets.',
 'OpenVLA adaptation1A6000, pi0 adaptation2A6000, per training tables.',
 'Do not read the typeset pi/4 as4 degrees. Dataset adaptations are not native OpenFly results; physical-flight evidence not established.',
 'https://github.com/valyentinee/IndoorUAV-Agent',
 'Final trained release not verified.',
 'Code license metadata absent; dataset/model terms unresolved.',category='dataset_benchmark')
add('huge','HUGE-Bench','Supporting task-suite evidence aligned with the architecture paper categories.',
 'High-level task to trajectory; 3DGS images and aligned mesh geometry.',
 'pi0.5 Avg.TCR0.581 and NDTW0.467; adapted OpenVLA0.112 and0.011 respectively.',
 'Trajectory coverage at1/2/5m, ordering-aware NDTW, stage progress, collision rate and collision-aware SPL; these values are not success percentages.',
 'Sections3.4-3.5 and4, Table2; Appendix A.',
 'Eight tasks, four digital twins;5,330train/593seen/294unseen trajectories.',
 'Isaac Sim with PhysX; scene reconstruction reported on RTX5090; model-training cost not verified here.',
 'Real-scene reconstruction remains simulation. Paper notes static-environment and real-deployment limitations; full release not confirmed by project homepage.',
 'https://jingyu198.github.io/HUGE_Bench/ (project)',licenses='Data/model licenses not verified.',category='dataset_benchmark')
add('aerialvla_dialogue','AerialVLA (Chen et al., AAAI dialogue)','Boundary case, kept outside the main15: assisted aerial-view navigation.',
 'Waypoint/stop/progress heads, BEV history and online clarification.',
 'AVDH unseen-test SR28.3%; AVDH-Full25.2%; online-dialogue unseen-validation26.2%.',
 'Aerial-view navigation; online-dialogue experiments use an oracle language agent with privileged goal/path information.',
 'Publisher PDF sections3-5, Tables1and3.',
 'AVDN/AVDH, AVDH-Full and UNOD; remote-sensing and dialogue data.',
 'LLaVA-OneVision Qwen2-7B/SigLIP; learned waypoint and progress heads.',
 'Not evidence of unassisted FPV real flight. Distinct paper from Xu et al. AerialVLA; paper/code action-head details require version audit.',
 'https://github.com/chenjinyubuaa/AerialVLA',
 'README has local weight paths; downloadable final checkpoint not verified.',
 'Code Apache-2.0; data/model permissions not verified.',category='related_solution')

payload={'review_date':'2026-09-19','scope':'15 drone/aerial learned architectures, 3 supporting aerial benchmarks, 1 assisted-navigation boundary case; no manipulator architecture included.','reported_not_reproduced':True,'works':works}
(OUT/'evidence.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
(OUT/'source_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
reasons={
 'litevla':'Methods/results inspected as reporting-quality check; unclear denominators/splits and partial closed-loop evidence. Not used for quantitative synthesis.',
 'aerialvln':'Foundational benchmark and recurrent VLN; not a modern pretrained VLA architecture in main count.',
 'onfly':'Training-free VLM plus verifier/planner; separate architecture family, not a learned aerial action policy.',
 'vlfly':'Goal retrieval and goal-conditioned controller; relevant alternative, screened out after15 direct policies.',
 'seepointfly':'Training-free VLM spatial pointing; exclude from learned-policy count.',
 'fly0':'Training-free geometric anchoring and planning; exclude from learned-policy count.',
 'traveluav':'Foundational OpenUAV/TravelUAV benchmark and assisted navigation; scope covered by retained descendants.',
 'cosflytrack':'Tracking dataset and adaptation study; outside selected three supporting benchmarks.',
 'uavvla':'Satellite-image mission planning; not egocentric flight action learning.',
 'semanticdecision':'Related aerial VLN architecture; screened after target15 reached, no quantitative result adopted.',
 'singer':'Relevant compact onboard language-conditioned policy; screened after target15 reached, no quantitative result adopted.',
 'airvla':'Aerial manipulation dual-action model; relevant different task category, outside present navigation/tracking comparison.'}
extra_titles={'cognitive':'CognitiveDrone: A VLA Model and Evaluation Benchmark for Real-Time Cognitive Task Solving and Reasoning in UAVs','racevla':'RaceVLA: VLA-based Racing Drone Navigation with Human-like Behaviour','aerialvln':'AerialVLN: Vision-and-Language Navigation for UAVs','traveluav':'Towards Realistic UAV Vision-Language Navigation: Platform, Benchmark, and Methodology','uavvla':'UAV-VLA: Vision-Language-Action System for Large Scale Aerial Mission Generation','aerialvla_dialogue':'AerialVLA (Chen et al.; AAAI2026)'}
kept={r['id']:r for r in works}; candidates=[]
for m in manifest:
 k=m['id'];title=extra_titles.get(k,m.get('metadata',{}).get('title') or k)
 candidates.append(dict(id=k,title=title,url=kept[k]['url'] if k in kept else ('https://arxiv.org/abs/'+m['version'] if m.get('version') else m['url']),screening='retained' if k in kept else 'excluded_from_main_review',inspection='methods_results' if k in kept or k=='litevla' else 'title_abstract',reason=kept[k]['category'] if k in kept else reasons.get(k,'Outside main15 scope.')))
(OUT/'candidates.json').write_text(json.dumps(candidates,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

lines=['# Drone VLA resource inventory — 2026-09-19','','Checked public project pages, repository READMEs/license metadata and linked model/dataset metadata. HTTP200 and file existence do not prove benchmark reproducibility. No weights or datasets downloaded. Missing license metadata is unresolved, not permission. `resource_checks.json` records URLs, revisions, timestamps and file samples.','', '| Work | Code/project | Weights | Licenses and limitations |','|---|---|---|---|']
for r in works:lines.append('| '+ ' | '.join([r['title'],r['code'],r['weights'],r['licenses']]).replace('\n',' ')+' |')
(OUT/'RESOURCES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Built',len(works),'evidence rows;',len(candidates),'screened candidates;',sum(r['main_architecture'] for r in works),'main architectures')
