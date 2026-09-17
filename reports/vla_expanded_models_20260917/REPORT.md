# D141 - Expanded-data models and official OpenFly transfer

Completed local400-update Smol500 and Qwen3-VL4B runs on the frozen expanded data;Smol256 reference reused. No AWS spending or physical flights.

## Local development results

|Model|Original visual|New visual|STOP exact|False STOP|Pilot gate|
|---|---:|---:|---:|---:|---|
|smol256|8/16|32/64|5/6|8/128|False|
|smol500|9/16|34/64|6/6|6/128|False|
|qwen|16/16|64/64|6/6|1/128|True|

Same400updates/1600exposures,balanced visual/motion/HOLD/STOP,seed132,r8,identical sample schedule. SmolBF16 vs QwenNF4;native tokenizers/processors differ. Cross-model CE magnitudes are not comparable. Four final checkpoint reload spots must match.

## Official OpenFly offline transfer

|Model|All|Seen|Unseen|Macro recall|False STOP|
|---|---:|---:|---:|---:|---:|
|smol256|0/51|0/41|0/10|0.000|0/38|
|smol500|0/51|0/41|0/10|0.000|0/38|
|qwen|1/51|1/41|0/10|0.010|0/38|
|openfly|12/51|8/41|4/10|0.135|0/38|

51decisions from14official evaluation trajectories,41seen/10unseen,selected deterministically before inference. Majority-forward reference26/51. Two unsupported negative annotationIDs excluded and logged. Exact image/pose/yaw/coarse-action alignment verified. No external rows admitted totraining.

This is an offline coarse-action diagnostic on expert-recorded observations,not an official full benchmark,exact action-amplitude comparison,or closed-loop flight success. OpenFlyusesNF4,training chat template,vln_norm,two preceding frames+current. Localadapters receive currentfront only with missingdowncamera/odometry explicit. No state fabricated;no future frames,targetactions or targetposes in prompts. Multi-stage instructions and missinghistory limit transfer interpretation.

## Local simulation flights

- smol500,seed1400: false_stop;success=False;distance=1.409m.
- smol500,seed1405: false_stop;success=False;distance=1.278m.
- qwen,seed1400: timeout;success=False;distance=0.540m.
- qwen,seed1405: timeout;success=False;distance=9.186m.

Simulation pauses during inference. Actualmodeloutputs drive the controller;teacher is evaluation reference. OpenFly was not flown in these local coordinate tasks. Native external simulation and real-world readiness remain untested.

## Evidence

SeePROTOCOL.md,openfly_data_audit.json,*_training_report.json,*_transfer_report.json,summary.json,loss_curves.png,*_flight_audit.json andui_check.json. Originalbaselines/splits andheld-outseeds1-40/protected1060-1064 preserved.

Review:http://127.0.0.1:8771/expanded_models.html